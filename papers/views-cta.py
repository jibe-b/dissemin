class CtaView(SlugDetailView):
    model = Cta
    template_name = 'cta/cta.html'
    view_name = 'copyright transfer aggreement'

    def publishers(self):
        publisher = self.object
        return Publisher.objects.filter(copyright__transfer__agreement=publisher).distinct()

    def get_object(self):
        queryset = self.get_queryset()
        pk = self.kwargs.get('pk', None)
        identifiers = self.kwargs.get('identifiers', None)
        copyright_transfer_aggreement = None
        try:
            if pk is not None:
                copyright_transfer_aggreement = queryset.get(pk=pk)
            elif identifiers is not None:
                pass
                # copyright_transfer_aggreement = get_by_identifiers(identifiers) # array
            else:
                raise AttributeError("Copyright Transfer Aggreement expects an identifier or a pk")
        except ObjectDoesNotExist:
            pass

        if not publisher:
            pass
            # publisher = Publisher.create_by_identifiers(identifiers) # array
            # if publisher is None:
            #     raise Http404(_("No %(verbose_name) found matching the query)") %
            #                  {'verbose_name': Publisher._meta.verbose_name})
        return publisher

    def context_data(self, **kwargs):
        context = super(CtaView, self).get_context_data(**kwargs)
        context['breadcrumbs'] = self.object.breadcrumbs()
        # TODO extract context
