from memoized import memoized

from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext as _, ugettext_lazy

from corehq.apps.enterprise.views import BaseEnterpriseAdminView
from corehq.apps.hqwebapp.async_handler import AsyncHandlerMixin
from corehq.apps.hqwebapp.decorators import use_jquery_ui
from corehq.apps.sso.aync_handlers import SSOExemptUsersAdminAsyncHandler
from corehq.apps.sso.certificates import get_certificate_response
from corehq.apps.sso.forms import SSOEnterpriseSettingsForm
from corehq.apps.sso.models import IdentityProvider
from corehq.toggles import ENTERPRISE_SSO


@method_decorator(ENTERPRISE_SSO.required_decorator(), name='dispatch')
class ManageSSOEnterpriseView(BaseEnterpriseAdminView):
    page_title = ugettext_lazy("Manage Single Sign-On")
    urlname = 'manage_sso'
    template_name = 'sso/enterprise_admin/manage_sso.html'

    @property
    def page_context(self):
        return {
            'identity_providers': IdentityProvider.objects.filter(
                owner=self.request.account, is_editable=True
            ).all(),
            'account': self.request.account,
        }


@method_decorator(ENTERPRISE_SSO.required_decorator(), name='dispatch')
class EditIdentityProviderEnterpriseView(BaseEnterpriseAdminView, AsyncHandlerMixin):
    page_title = ugettext_lazy("Edit Identity Provider")
    urlname = 'edit_idp_enterprise'
    template_name = 'sso/enterprise_admin/edit_identity_provider.html'
    async_handlers = [
        SSOExemptUsersAdminAsyncHandler,
    ]

    @use_jquery_ui  # for datepicker
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    @property
    def page_url(self):
        return reverse(self.urlname, args=(self.domain, self.idp_slug))

    @property
    @memoized
    def idp_slug(self):
        return self.kwargs['idp_slug']

    @property
    def parent_pages(self):
        return [
            {
                'title': ManageSSOEnterpriseView.page_title,
                'url': reverse('manage_sso', args=(self.domain,)),
            },
        ]

    @property
    def page_context(self):
        return {
            'edit_idp_form': self.edit_enterprise_idp_form,
            'idp_slug': self.idp_slug,
        }

    @property
    @memoized
    def identity_provider(self):
        try:
            return IdentityProvider.objects.get(
                slug=self.idp_slug, owner=self.request.account, is_editable=True
            )
        except ObjectDoesNotExist:
            raise Http404()

    def get(self, request, *args, **kwargs):
        if 'sp_cert_public' in request.GET:
            return get_certificate_response(
                self.identity_provider.sp_cert_public,
                f"{self.identity_provider.slug}_sp_public.cert"
            )
        if 'sp_rollover_cert_public' in request.GET:
            return get_certificate_response(
                self.identity_provider.sp_rollover_cert_public,
                f"{self.identity_provider.slug}_sp_rollover_public.cert"
            )
        return super().get(request, args, kwargs)

    @property
    @memoized
    def edit_enterprise_idp_form(self):
        if self.request.method == 'POST' and not self.is_deletion_request:
            return SSOEnterpriseSettingsForm(self.identity_provider, self.request.POST)
        return SSOEnterpriseSettingsForm(self.identity_provider)

    def post(self, request, *args, **kwargs):
        if self.async_response is not None:
            return self.async_response
        if self.edit_enterprise_idp_form.is_valid():
            pass
            # todo
        return self.get(request, *args, **kwargs)

