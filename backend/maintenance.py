# -*- encoding: utf-8 -*-

# Dissemin: open access policy enforcement tool
# Copyright (C) 2014 Antonin Delpeuch
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#

"""
This module contains functions that are not normally needed
to run the platform, but that can be useful during development,
or to cleanup various things in the database.

These functions are not integrated in the rest of the platform,
so running them involves starting a Django shell ("python manage.py shell"),
importing this module and running the function manually.
"""

from __future__ import unicode_literals

from collections import defaultdict
from bulk_update.helper import bulk_update

import backend.crossref
from backend.romeo import fetch_publisher
from backend.tasks import change_publisher_oa_status
from papers.models import Name
from papers.models import NameVariant
from papers.models import OaiRecord
from papers.models import Paper
from papers.models import Researcher
from papers.utils import sanitize_html
from publishers.models import AliasPublisher
from publishers.models import Publisher
from datetime import datetime
from elasticsearch.helpers import bulk
import haystack
from haystack.exceptions import SkipDocument
from haystack.constants import ID

def update_index_for_model(model, batch_size=256, batches_per_commit=10, firstpk=0):
    """
    More efficient update of the search index for large models such as
    Paper

    :param batch_size: the number of instances to retrieve for each query
    :param batches_per_commit: the number of batches after which we
                    should commit to the search engine
    :param firstpk: the instance to start with.
    """
    using_backends = haystack.connection_router.for_write()
    if len(using_backends) != 1:
        raise ValueError("Don't know what search index to use")
    engine = haystack.connections[using_backends[0]]
    backend = engine.get_backend()
    index = engine.get_unified_index().get_index(model)

    qs = model.objects.order_by('pk')
    lastpk_object = list(model.objects.order_by('-pk')[:1])

    if not lastpk_object: # No object in the model
        return

    lastpk = lastpk_object[0].pk

    batch_number = 0

    # rate reporting
    indexed = 0
    starttime = datetime.utcnow()

    while firstpk < lastpk:
        batch_number += 1

        prepped_docs = []
        for obj in qs.filter(pk__gt=firstpk)[:batch_size]:
            firstpk = obj.pk

            try:
                prepped_data = index.full_prepare(obj)
                final_data = {}

                # Convert the data to make sure it's happy.
                for key, value in prepped_data.items():
                    final_data[key] = backend._from_python(value)
                final_data['_id'] = final_data[ID]

                prepped_docs.append(final_data)
            except SkipDocument:
                continue

        bulk(backend.conn, prepped_docs, index=backend.index_name, doc_type='modelresult')
        indexed += len(prepped_docs)
        if batch_number % batches_per_commit == 0:
            backend.conn.indices.refresh(index=backend.index_name)

        if indexed >= 5000:
            curtime = datetime.utcnow()
            rate = int(indexed / (curtime-starttime).total_seconds())
            print "%d obj/s, %d / %d" % (rate,firstpk,lastpk)
            starttime = curtime
            indexed = 0

def enumerate_large_qs(queryset, key='pk', batch_size=256):
    """
    Enumerates a large queryset (milions of rows) efficiently
    """
    lastval = None
    found = True

    while found:
        sliced = queryset.order_by(key)
        if lastval is not None:
            sliced = sliced.filter(**{key+'__gt':lastval})
        print lastval
        sliced = sliced[:batch_size]

        found = False
        for elem in sliced:
            found = True
            lastval = getattr(elem, key)
            yield elem

def update_availability():
    for paper in enumerate_large_qs(Paper.objects.filter(oa_status='UNK')):
        paper.update_availability()
        if paper.oa_status != 'UNK':
            paper.update_index()

def cleanup_researchers():
    """
    Deletes all the researchers who have not authored any paper.
    """
    deleted_count = 0
    for p in Researcher.objects.all():
        nb_papers = p.papers.count()
        if not nb_papers:
            deleted_count += 1
            p.delete()
    print "Deleted "+str(deleted_count)+" researchers"


def cleanup_names(dry_run=False):
    """
    Deletes all the names that are not linked to any researcher
    """
    deleted_count = 0
    for n in Name.objects.all():
        if NameVariant.objects.filter(name=n).count() == 0:
            deleted_count += 1
            if not dry_run:
                n.delete()
    print "Deleted "+str(deleted_count)+" names"


def merge_names(fro, to):
    """
    Merges the name object 'fro' into 'to
    """
    Researcher.objects.filter(name_id=fro.id).update(name_id=to.id)
    NameVariant.objects.filter(name_id=fro.id).update(name_id=to.id)
    fro.delete()


def update_paper_statuses():
    """
    Should only be run if something went wrong,
    the backend is supposed to update the fields by itself
    """
    papers = Paper.objects.all()
    for p in papers:
        p.update_availability()


def cleanup_titles():
    """
    Run HTML sanitizing on all the titles of the papers
    (this is normally done on creation of the papers, but
    not for old dumps of the database)
    """
    papers = Paper.objects.all()
    for p in papers:
        p.title = sanitize_html(p.title)
        p.save(update_fields=['title'])


def cleanup_abstracts():
    """
    Run HTML sanitizing on the abstracts
    (this is normally done on creation of the papers, but
    not for old dumps of the database)
    """
    for p in OaiRecord.objects.all():
        if p.description:
            new_abstract = sanitize_html(p.description)
            if new_abstract != p.description:
                p.description = new_abstract
                p.save()


def recompute_fingerprints():
    """
    Recomputes the fingerprints of all papers, merging
    those who end up having the same fingerprint
    """
    merged = 0
    for idx, p in enumerate(Paper.objects.all()):
        if idx % 100 == 0:
            print idx
        p.fingerprint = 'blah'
        match = p.recompute_fingerprint_and_merge_if_needed()
        if match is not None:
            merged += 1
    print "%d papers merged" % merged


def find_collisions():
    """
    Recomputes all the fingerprints and reports those which would be
    merged by recompute_fingerprints()
    """
    dct = defaultdict(set)
    for p in Paper.objects.all():
        fp = p.new_fingerprint()
        dct[fp].add(p)

    for fp, s in dct.items():
        if len(s) > 1:
            first = True
            for paper in s:
                if first:
                    first = False
                    print "### "+paper.plain_fingerprint()
                print paper.title
                print paper.bare_author_names()


def create_publisher_aliases(erase_existing=True):
    # TODO: this might be more efficient with aggregates?
    counts = defaultdict(int)
    for p in OaiRecord.objects.all():
        if p.publisher_id:
            pair = (p.publisher_name, p.publisher_id)
            counts[pair] += 1

    if erase_existing:
        AliasPublisher.objects.all().delete()

    for (name, pk) in counts:
        if not erase_existing:
            alias = AliasPublisher.objects.get_or_create(
                name=name, publisher_id=pk)
        else:
            alias = AliasPublisher(name=name, publisher_id=pk)
        alias.count = counts[(name, pk)]
        alias.save()


def refetch_publishers():
    """
    Tries to assign publishers to OaiRecords without Journals
    """
    for p in OaiRecord.objects.filter(publisher__isnull=True, publisher_name__isnull=False):
        publisher = fetch_publisher(p.publisher_name)
        if publisher:
            p.publisher = publisher
            p.save(update_fields=['publisher'])
            p.paper.update_availability()


def refetch_containers():
    """
    Tries to assign containers to OaiRecords without containers
    """
    # TODO
    for p in OaiRecord.objects.filter(container__isnull=True):
        metadata = backend.crossref.fetch_metadata_by_DOI(p.doi)
        if metadata is None:
            continue
        p.container = metadata.get('container-title')
        if p.container:
            p.save()


def recompute_publisher_policies():
    """
    Recomputes the publisher policy according to some possibly new criteria
    """
    for p in Publisher.objects.all():
        change_publisher_oa_status(p.pk, p.classify_oa_status())

def cleanup_paper_researcher_ids():
    """
    Ensures that all researcher_ids in Papers link to actual researchers
    """
    researcher_ids = set(Researcher.objects.all().values_list('id', flat=True))
    bs = 1000
    curid = 0
    found = True
    while found:
        found = False
        batch = []
        for p in Paper.objects.filter(id__gt=curid).order_by('id')[:bs]:
            curid = p.id
            found = True
            modified = False
            for i, author in enumerate(p.authors_list):
                rid = author['researcher_id']
                if (rid is not None and rid not in researcher_ids):
                    p.authors_list[i]['researcher_id'] = None
                modified = True
            if modified:
                batch.append(p)
        print "Updating %d papers" % len(batch)
        bulk_update(batch)
