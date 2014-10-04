from django.db import models
from django.core.exceptions import ObjectDoesNotExist
from papers.utils import nstr

# Information about the researchers and their groups
class Department(models.Model):
    name = models.CharField(max_length=300)

    def __unicode__(self):
        return self.name

class ResearchGroup(models.Model):
    name = models.CharField(max_length=300)

    def __unicode__(self):
        return self.name

class Researcher(models.Model):
    department = models.ForeignKey(Department)
    groups = models.ManyToManyField(ResearchGroup,blank=True,null=True)
    email = models.EmailField(blank=True,null=True)

    # DOI search
    last_doi_search = models.DateTimeField(null=True,blank=True)
    status = models.CharField(max_length=512, blank=True, null=True)
    last_status_update = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        first_name = Name.objects.filter(researcher_id=self.id).order_by('id').first()
        if first_name:
            return unicode(first_name)
        return "Anonymous researcher"

    @property
    def authors_by_year(self):
        return Author.objects.filter(name__researcher_id=self.id).order_by('-paper__year')
    @property
    def names(self):
        return self.name_set.order_by('id')
    @property
    def name(self):
        name = self.names.first()
        if name:
            return name
        else:
            return "Anonymous researcher"
    @property
    def aka(self):
        return self.names[:2]

class Name(models.Model):
    researcher = models.ForeignKey(Researcher, blank=True, null=True)
    first = models.CharField(max_length=256)
    last = models.CharField(max_length=256)
    unique_together = ('first','last')# TODO Two researchers with the same name is not supported
    def __unicode__(self):
        return '%s %s' % (self.first,self.last)
    @property
    def is_known(self):
        return self.researcher != None

# Papers matching one or more researchers
class Paper(models.Model):
    title = models.CharField(max_length=1024)
    fingerprint = models.CharField(max_length=64)
    year = models.IntegerField()
    last_modified = models.DateField(auto_now=True)
    def __unicode__(self):
        return self.title
    
class Author(models.Model):
    paper = models.ForeignKey(Paper)
    name = models.ForeignKey(Name)
    def __unicode__(self):
        return unicode(self.name)

# Publisher associated with a journal
class Publisher(models.Model):
    romeo_id = models.CharField(max_length=64)
    name = models.CharField(max_length=256)
    alias = models.CharField(max_length=256,null=True,blank=True)
    url = models.URLField(null=True,blank=True)
    preprint = models.CharField(max_length=32)
    postprint = models.CharField(max_length=32)
    pdfversion = models.CharField(max_length=32)
    def __unicode__(self):
        return self.name
    @property
    def publi_count(self):
        count = 0
        for journal in self.journal_set.all():
            count += journal.publication_set.count()
        return count
    @property
    def preprint_conditions(self):
        return self.publisherrestrictiondetail_set.filter(applies_to='preprint')
    @property
    def postprint_conditions(self):
        return self.publisherrestrictiondetail_set.filter(applies_to='postprint')
    @property
    def pdfversion_conditions(self):
        return self.publisherrestrictiondetail_set.filter(applies_to='pdfversion')

# Journal data retrieved from RoMEO
class Journal(models.Model):
    title = models.CharField(max_length=256)
    last_updated = models.DateTimeField(auto_now=True)
    issn = models.CharField(max_length=10, blank=True, null=True, unique=True)
    publisher = models.ForeignKey(Publisher)
    def __unicode__(self):
        return self.title

class PublisherCondition(models.Model):
    publisher = models.ForeignKey(Publisher)
    text = models.CharField(max_length=1024)
    def __unicode__(self):
        return self.text

class PublisherCopyrightLink(models.Model):
    publisher = models.ForeignKey(Publisher)
    text = models.CharField(max_length=256)
    url = models.URLField()
    def __unicode__(self):
        return self.text

class PublisherRestrictionDetail(models.Model):
    publisher = models.ForeignKey(Publisher)
    text = models.CharField(max_length=256)
    applies_to = models.CharField(max_length=32)
    def __unicode__(self):
        return self.text

# Publication of these papers (in journals or conference proceedings)
class Publication(models.Model):
    paper = models.ForeignKey(Paper)
    pubtype = models.CharField(max_length=64)
    title = models.CharField(max_length=256) # this is actually the *journal* title
    journal = models.ForeignKey(Journal, blank=True, null=True)
    issue = models.CharField(max_length=64, blank=True, null=True)
    volume = models.CharField(max_length=64, blank=True, null=True)
    pages = models.CharField(max_length=64, blank=True, null=True)
    date = models.CharField(max_length=128, blank=True, null=True)
    publisher = models.CharField(max_length=256, blank=True, null=True)
    doi = models.CharField(max_length=1024, unique=True, blank=True, null=True) # in theory, there is no limit

    def details_to_str(self):
        result = ''
        if self.issue or self.volume or self.pages or self.date:
            result += ', '
        if self.issue:
            result += self.issue
        if self.volume:
            result += '('+self.volume+')'
        if self.issue or self.volume:
            result += ', '
        if self.pages:
            result += self.pages+', '
        if self.date:
            result += self.date
        return result

    def __unicode__(self):
        return self.title+self.details_to_str()

# Rough data extracted through OAI-PMH
class OaiSource(models.Model):
    url = models.CharField(max_length=300)
    name = models.CharField(max_length=100)
    prefix_identifier = models.CharField(max_length=256)
    prefix_url = models.CharField(max_length=256)
    restrict_set = models.CharField(max_length=256, null=True, blank=True)

    # Fetching properties
    last_update = models.DateTimeField()
    last_status_update = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=512, null=True, blank=True)
    def __unicode__(self):
        return self.name

class OaiRecord(models.Model):
    source = models.ForeignKey(OaiSource)
    identifier = models.CharField(max_length=512, unique=True)
    url = models.CharField(max_length=1024)
    about = models.ForeignKey(Paper)
    def __unicode__(self):
        return self.identifier



