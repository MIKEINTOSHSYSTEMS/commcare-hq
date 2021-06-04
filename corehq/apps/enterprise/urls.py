from django.conf.urls import url

from corehq.apps.enterprise.views import (
    edit_enterprise_settings,
    enterprise_dashboard,
    enterprise_dashboard_download,
    enterprise_dashboard_email,
    enterprise_dashboard_total,
    enterprise_settings,
)
from corehq.apps.enterprise.views import EnterpriseBillingStatementsView
from corehq.apps.sso.views.enterprise_admin import (
    ManageSSOEnterpriseView,
    EditIdentityProviderEnterpriseView,
)
from corehq.apps.users.views import enterprise_permissions

domain_specific = [
    url(r'^dashboard/$', enterprise_dashboard, name='enterprise_dashboard'),
    url(r'^dashboard/(?P<slug>[^/]*)/download/(?P<export_hash>[\w\-]+)/$', enterprise_dashboard_download,
        name='enterprise_dashboard_download'),
    url(r'^dashboard/(?P<slug>[^/]*)/email/$', enterprise_dashboard_email,
        name='enterprise_dashboard_email'),
    url(r'^dashboard/(?P<slug>[^/]*)/total/$', enterprise_dashboard_total,
        name='enterprise_dashboard_total'),
    url(r'^permissions/$', enterprise_permissions, name="enterprise_permissions"),
    url(r'^settings/$', enterprise_settings, name='enterprise_settings'),
    url(r'^settings/edit/$', edit_enterprise_settings, name='edit_enterprise_settings'),
    url(r'^billing_statements/$', EnterpriseBillingStatementsView.as_view(),
        name=EnterpriseBillingStatementsView.urlname),
    url(r'^sso/$', ManageSSOEnterpriseView.as_view(),
        name=ManageSSOEnterpriseView.urlname),
    url(r'^sso/(?P<idp_slug>[^/]*)/$', EditIdentityProviderEnterpriseView.as_view(),
        name=EditIdentityProviderEnterpriseView.urlname),
]
