# coding=utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import division

import datetime

from dateutil import relativedelta
from django.utils.functional import cached_property

from corehq.apps.hqwebapp.decorators import use_nvd3
from corehq.apps.locations.models import SQLLocation
from corehq.apps.reports.datatables import DataTablesHeader, DataTablesColumn
from corehq.apps.reports.graph_models import MultiBarChart, Axis
from corehq.apps.reports.standard import ProjectReportParametersMixin, CustomProjectReport, DatespanMixin
from custom.intrahealth.filters import YeksiNaaLocationFilter, ProgramsAndProductsFilter, DateRangeFilter
from custom.intrahealth.sqldata import TauxDeRuptureRateData
from dimagi.utils.dates import force_to_date


class TauxDeRuptureReport(CustomProjectReport, DatespanMixin, ProjectReportParametersMixin):
    name = "Taux De Rupture"
    slug = 'taux_de_rupture_report'
    comment = 'test comment change me later'
    default_rows = 10

    report_template_path = 'yeksi_naa/tabular_report.html'

    @use_nvd3
    def decorator_dispatcher(self, request, *args, **kwargs):
        super(TauxDeRuptureReport, self).decorator_dispatcher(request, *args, **kwargs)

    @property
    def fields(self):
        return [DateRangeFilter, ProgramsAndProductsFilter, YeksiNaaLocationFilter]

    @cached_property
    def rendered_report_title(self):
        return self.name

    @property
    def report_context(self):
        context = {
            'report': self.get_report_context(),
            'title': self.name
        }

        return context

    @property
    def selected_location(self):
        try:
            return SQLLocation.objects.get(location_id=self.request.GET.get('location_id'))
        except SQLLocation.DoesNotExist:
            return None

    @property
    def selected_location_type(self):
        if self.selected_location:
            location_type = self.selected_location.location_type.code
            if location_type == 'region':
                return 'District'
            else:
                return 'PPS'
        else:
            return 'Region'

    @property
    def headers(self):
        return DataTablesHeader(
            DataTablesColumn(self.selected_location_type),
            DataTablesColumn(
                'Méthode de calcul: nbre de PPS avec le produit disponsible sur le nbre total de PPS visités de la période'
            ),
        )

    def get_report_context(self):
        if self.needs_filters:
            headers = []
            rows = []
        else:
            rows = self.calculate_rows()
            headers = self.headers

        context = dict(
            report_table=dict(
                title=self.name,
                slug=self.slug,
                comment=self.comment,
                headers=headers,
                rows=rows,
                default_rows=self.default_rows,
            )
        )

        return context

    def calculate_rows(self):
        # TODO: needs further implementation
        rows = TauxDeRuptureRateData(config=self.config).rows
        return rows

    @property
    def charts(self):
        chart = MultiBarChart(None, Axis('Location'), Axis('Percent', format='.2f'))
        chart.height = 400
        chart.marginBottom = 100

        def get_data_for_graph():
            com = []
            rows = self.calculate_rows()
            for row in rows:
                com.append({"x": row[0], "y": row[1]['sort_key']})

            return [
                {
                    "key": "'Méthode de calcul: nbre de PPS avec le produit disponsible sur le nbre total de PPS visités de la période'",
                    'values': com
                },
            ]

        chart.data = get_data_for_graph()
        return [chart]

    @property
    def config(self):
        config = dict(
            domain=self.domain,
        )
        if self.request.GET.get('startdate'):
            startdate = force_to_date(self.request.GET.get('startdate'))
        else:
            startdate = datetime.datetime.now().date() - relativedelta(days=1)
        if self.request.GET.get('enddate'):
            enddate = force_to_date(self.request.GET.get('enddate'))
        else:
            enddate = datetime.datetime.now()
        config['startdate'] = startdate
        config['enddate'] = enddate
        config['product_program'] = self.request.GET.get('product_program')
        config['product_product'] = self.request.GET.get('product_product')
        config['selected_location'] = self.request.GET.get('location_id')
        return config
