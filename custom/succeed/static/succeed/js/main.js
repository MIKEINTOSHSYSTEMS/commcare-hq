hqDefine("succeed/js/main", function () {
        $(function() {
        {% if report_table and report_table.datatables %}
            var reportTables = hqImport("reports/js/config.dataTables.bootstrap").HQReportDataTables({
                dataTableElem: '#report_table_{{ report.slug }}',
                defaultRows: {{ report_table.default_rows|default:10 }},
                startAtRowNum: {{ report_table.start_at_row|default:0 }},
                showAllRowsOption: {{ report_table.show_all_rows|JSON }},

                {% if report_table.headers.render_aoColumns %}aoColumns: {{ report_table.headers.render_aoColumns|JSON }},{% endif %}
                autoWidth: {{ report_table.headers.auto_width|JSON }},
                {% if report_table.headers.custom_sort %}customSort: {{ report_table.headers.custom_sort|JSON }},{% endif %}

                {% if report_table.pagination.hide %}
                show_pagination: false,
                {% endif %}

                {% if report_table.pagination.is_on %}
                    ajaxSource: '{{ report_table.pagination.source }}',
                    ajaxParams: {{ report_table.pagination.params|JSON }},
                {% endif %}

                {% if report_table.bad_request_error_text %}
                    badRequestErrorText: "<span class='label label-danger'>Sorry!</span> {{ report_table.bad_request_error_text }}",
                {% endif %}

                {% if report_table.left_col.is_fixed %}
                    fixColumns: true,
                    fixColsNumLeft: {{ report_table.left_col.fixed.num }},
                    fixColsWidth: {{ report_table.left_col.fixed.width }},
                {% endif %}
                includeFilter: true,
                aaSorting: [[5, 'asc']],
            });
            var standardHQReport = hqImport("reports/js/standard_hq_report").getStandardHQReport();
            if (typeof standardHQReport !== 'undefined') {
                standardHQReport.handleTabularReportCookies(reportTables);
            }
            reportTables.render();
        {% endif %}

            $('.header-popover').popout({
                trigger: 'hover',
                placement: 'bottom'
            });
        });
});
