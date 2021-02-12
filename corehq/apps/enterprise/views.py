import json

from django.conf import settings
from django.contrib import messages
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Sum
from django.http import (
    HttpResponse,
    HttpResponseNotFound,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import ugettext as _, ugettext_lazy
from django.views.decorators.http import require_POST

from django_prbac.utils import has_privilege
from memoized import memoized

from corehq.apps.accounting.decorators import always_allow_project_access
from couchexport.export import Format
from dimagi.utils.couch.cache.cache_core import get_redis_client

from corehq import privileges
from corehq.apps.accounting.models import CustomerInvoice, CustomerBillingRecord
from corehq.apps.accounting.utils import get_customer_cards, quantize_accounting_decimal, log_accounting_error
from corehq.apps.domain.views import DomainAccountingSettings
from corehq.apps.domain.views.accounting import PAYMENT_ERROR_MESSAGES, InvoiceStripePaymentView, \
    BulkStripePaymentView, WireInvoiceView, BillingStatementPdfView

from corehq.apps.enterprise.enterprise import EnterpriseReport

from corehq.apps.enterprise.forms import (
    EnterpriseSettingsForm,
)
from corehq.apps.enterprise.tasks import email_enterprise_report

from corehq.apps.domain.decorators import (
    login_and_domain_required,
)

from corehq.apps.accounting.utils.subscription import get_account_or_404
from corehq.apps.export.utils import get_default_export_settings_for_domain
from corehq.apps.hqwebapp.views import CRUDPaginatedViewMixin
from corehq.const import USER_DATE_FORMAT


@always_allow_project_access
@login_and_domain_required
def enterprise_dashboard(request, domain):
    account = get_account_or_404(request, domain)

    if not has_privilege(request, privileges.PROJECT_ACCESS):
        return HttpResponseRedirect(reverse(EnterpriseBillingStatementsView.urlname, args=(domain,)))

    context = {
        'account': account,
        'domain': domain,
        'reports': [EnterpriseReport.create(slug, account.id, request.couch_user) for slug in (
            EnterpriseReport.DOMAINS,
            EnterpriseReport.WEB_USERS,
            EnterpriseReport.MOBILE_USERS,
            EnterpriseReport.FORM_SUBMISSIONS,
        )],
        'current_page': {
            'page_name': _('Enterprise Dashboard'),
            'title': _('Enterprise Dashboard'),
        }
    }
    return render(request, "enterprise/enterprise_dashboard.html", context)


@login_and_domain_required
def enterprise_dashboard_total(request, domain, slug):
    account = get_account_or_404(request, domain)
    report = EnterpriseReport.create(slug, account.id, request.couch_user)
    return JsonResponse({'total': report.total})


@login_and_domain_required
def enterprise_dashboard_download(request, domain, slug, export_hash):
    account = get_account_or_404(request, domain)
    report = EnterpriseReport.create(slug, account.id, request.couch_user)

    redis = get_redis_client()
    content = redis.get(export_hash)

    if content:
        file = ContentFile(content)
        response = HttpResponse(file, Format.FORMAT_DICT[Format.UNZIPPED_CSV])
        response['Content-Length'] = file.size
        response['Content-Disposition'] = 'attachment; filename="{}"'.format(report.filename)
        return response

    return HttpResponseNotFound(_("That report was not found. Please remember that "
                                  "download links expire after 24 hours."))


@login_and_domain_required
def enterprise_dashboard_email(request, domain, slug):
    account = get_account_or_404(request, domain)
    report = EnterpriseReport.create(slug, account.id, request.couch_user)
    email_enterprise_report.delay(domain, slug, request.couch_user)
    message = _("Generating {title} report, will email to {email} when complete.").format(**{
        'title': report.title,
        'email': request.couch_user.username,
    })
    return JsonResponse({'message': message})


@login_and_domain_required
def enterprise_settings(request, domain):
    account = get_account_or_404(request, domain)
    export_settings = get_default_export_settings_for_domain(domain)

    if request.method == 'POST':
        form = EnterpriseSettingsForm(request.POST, domain=domain, account=account,
                                      export_settings=export_settings)
    else:
        form = EnterpriseSettingsForm(domain=domain, account=account, export_settings=export_settings)

    context = {
        'account': account,
        'accounts_email': settings.ACCOUNTS_EMAIL,
        'domain': domain,
        'restrict_signup': request.POST.get('restrict_signup', account.restrict_signup),
        'current_page': {
            'title': _('Enterprise Settings'),
            'page_name': _('Enterprise Settings'),
        },
        'settings_form': form,
    }
    return render(request, "enterprise/enterprise_settings.html", context)


@login_and_domain_required
@require_POST
def edit_enterprise_settings(request, domain):
    account = get_account_or_404(request, domain)
    export_settings = get_default_export_settings_for_domain(domain)
    form = EnterpriseSettingsForm(request.POST, domain=domain, account=account, export_settings=export_settings)

    if form.is_valid():
        form.save(account)
        messages.success(request, "Account successfully updated.")
    else:
        return enterprise_settings(request, domain)

    return HttpResponseRedirect(reverse('enterprise_settings', args=[domain]))


class EnterpriseBillingStatementsView(DomainAccountingSettings, CRUDPaginatedViewMixin):
    template_name = 'domain/billing_statements.html'
    urlname = 'enterprise_billing_statements'
    page_title = ugettext_lazy("Billing Statements")

    limit_text = ugettext_lazy("statements per page")
    empty_notification = ugettext_lazy("No Billing Statements match the current criteria.")
    loading_message = ugettext_lazy("Loading statements...")

    @property
    def stripe_cards(self):
        return get_customer_cards(self.request.user.username, self.domain)

    @property
    def show_hidden(self):
        if not self.request.user.is_superuser:
            return False
        return bool(self.request.POST.get('additionalData[show_hidden]'))

    @property
    def show_unpaid(self):
        try:
            return json.loads(self.request.POST.get('additionalData[show_unpaid]'))
        except TypeError:
            return False

    @property
    def invoices(self):
        account = self.account or get_account_or_404(self.request, self.request.domain)
        invoices = CustomerInvoice.objects.filter(account=account)
        if not self.show_hidden:
            invoices = invoices.filter(is_hidden=False)
        if self.show_unpaid:
            invoices = invoices.filter(date_paid__exact=None)
        return invoices.order_by('-date_start', '-date_end')

    @property
    def total(self):
        return self.paginated_invoices.count

    @property
    @memoized
    def paginated_invoices(self):
        return Paginator(self.invoices, self.limit)

    @property
    def total_balance(self):
        """
        Returns the total balance of unpaid, unhidden invoices.
        Doesn't take into account the view settings on the page.
        """
        account = self.account or get_account_or_404(self.request, self.request.domain)
        invoices = (CustomerInvoice.objects
                    .filter(account=account)
                    .filter(date_paid__exact=None)
                    .filter(is_hidden=False))
        return invoices.aggregate(
            total_balance=Sum('balance')
        ).get('total_balance') or 0.00

    @property
    def column_names(self):
        return [
            _("Statement No."),
            _("Billing Period"),
            _("Date Due"),
            _("Payment Status"),
            _("PDF"),
        ]

    @property
    def page_context(self):
        pagination_context = self.pagination_context
        pagination_context.update({
            'stripe_options': {
                'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
                'stripe_cards': self.stripe_cards,
            },
            'payment_error_messages': PAYMENT_ERROR_MESSAGES,
            'payment_urls': {
                'process_invoice_payment_url': reverse(
                    InvoiceStripePaymentView.urlname,
                    args=[self.domain],
                ),
                'process_bulk_payment_url': reverse(
                    BulkStripePaymentView.urlname,
                    args=[self.domain],
                ),
                'process_wire_invoice_url': reverse(
                    WireInvoiceView.urlname,
                    args=[self.domain],
                ),
            },
            'total_balance': self.total_balance,
            'show_plan': False
        })
        return pagination_context

    @property
    def can_pay_invoices(self):
        return self.request.couch_user.is_domain_admin(self.domain)

    @property
    def paginated_list(self):
        for invoice in self.paginated_invoices.page(self.page).object_list:
            try:
                last_billing_record = CustomerBillingRecord.objects.filter(
                    invoice=invoice
                ).latest('date_created')
                if invoice.is_paid:
                    payment_status = (_("Paid on %s.")
                                      % invoice.date_paid.strftime(USER_DATE_FORMAT))
                    payment_class = "label label-default"
                else:
                    payment_status = _("Not Paid")
                    payment_class = "label label-danger"
                date_due = (
                    (invoice.date_due.strftime(USER_DATE_FORMAT)
                     if not invoice.is_paid else _("Already Paid"))
                    if invoice.date_due else _("None")
                )
                yield {
                    'itemData': {
                        'id': invoice.id,
                        'invoice_number': invoice.invoice_number,
                        'start': invoice.date_start.strftime(USER_DATE_FORMAT),
                        'end': invoice.date_end.strftime(USER_DATE_FORMAT),
                        'plan': None,
                        'payment_status': payment_status,
                        'payment_class': payment_class,
                        'date_due': date_due,
                        'pdfUrl': reverse(
                            BillingStatementPdfView.urlname,
                            args=[self.domain, last_billing_record.pdf_data_id]
                        ),
                        'canMakePayment': (not invoice.is_paid
                                           and self.can_pay_invoices),
                        'balance': "%s" % quantize_accounting_decimal(invoice.balance),
                    },
                    'template': 'statement-row-template',
                }
            except CustomerBillingRecord.DoesNotExist:
                log_accounting_error(
                    "An invoice was generated for %(invoice_id)d "
                    "(domain: %(domain)s), but no billing record!" % {
                        'invoice_id': invoice.id,
                        'domain': self.domain,
                    },
                    show_stack_trace=True
                )

    def refresh_item(self, item_id):
        pass

    def post(self, *args, **kwargs):
        return self.paginate_crud_response
