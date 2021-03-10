from contextlib import contextmanager
from unittest.mock import patch

from django.conf import settings as default_settings
from django.test import SimpleTestCase
from testil import Config, eq

from .. import middleware as mod


class TestAuditMiddleware(SimpleTestCase):

    def setUp(self):
        self.request = Config(user="username")

    def test_generic_view_not_audited_with_default_settings(self):
        func = make_view()
        with configured_middleware() as ware:
            ware.process_view(self.request, func, ARGS, KWARGS)
        self.assert_no_audit(self.request)

    def test_admin_view_is_audited_with_default_settings(self):
        func = make_view(module="django.contrib.admin")
        with configured_middleware() as ware:
            ware.process_view(self.request, func, ARGS, KWARGS)
        self.assert_audit(self.request)

    def test_generic_view_is_audited_with_audit_all_views_setting(self):
        func = make_view()
        settings = Settings(AUDIT_ALL_VIEWS=True)
        with configured_middleware(settings) as ware:
            ware.process_view(self.request, func, ARGS, KWARGS)
        self.assert_audit(self.request)

    def test_generic_view_class_is_audited_with_audit_all_views_setting(self):
        func = make_view("ClassView")
        settings = Settings(AUDIT_ALL_VIEWS=True)
        with configured_middleware(settings) as ware:
            ware.process_view(self.request, func, ARGS, KWARGS)
        self.assert_audit(self.request)

    def test_audit_views_setting(self):
        func = make_view("ChangeMyPasswordView", "corehq.apps.settings.views")
        with configured_middleware() as ware:
            ware.process_view(self.request, func, ARGS, KWARGS)
        self.assert_audit(self.request)

    def test_audit_modules_setting(self):
        func = make_view("ClassView", "corehq.apps.reports")
        with configured_middleware() as ware:
            ware.process_view(self.request, func, ARGS, KWARGS)
        self.assert_audit(self.request)

    def test_debug_media_view_not_audited(self):
        func = make_view("debug_media", "debug_toolbar.views")
        with configured_middleware() as ware:
            ware.process_view(self.request, func, ARGS, KWARGS)
        self.assert_no_audit(self.request)

    def test_staticfiles_not_audited(self):
        from django.contrib.staticfiles.views import serve
        with configured_middleware() as ware:
            ware.process_view(self.request, serve, ARGS, KWARGS)
        self.assert_no_audit(self.request)

    def test_process_response_without_audit_doc(self):
        with configured_middleware() as ware:
            ware(self.request)
        assert not hasattr(self.request, "audit_doc")

    def test_process_response_with_audit_doc_with_user(self):
        self.request.audit_doc = audit_doc = fake_audit_doc(user="username")
        with configured_middleware() as ware:
            ware(self.request)
        self.assertEqual(audit_doc.status_code, 200)
        self.assertEqual(audit_doc.user, "username")
        self.assertEqual(audit_doc.save.count, 1)

    def test_process_response_with_audit_doc_and_audit_user(self):
        self.request.audit_doc = audit_doc = fake_audit_doc(user=None)
        self.request.audit_user = "audit_user"
        with configured_middleware() as ware:
            ware(self.request)
        self.assertEqual(audit_doc.status_code, 200)
        self.assertEqual(audit_doc.user, "audit_user")
        self.assertEqual(audit_doc.save.count, 1)

    def test_process_response_with_audit_doc_and_couch_user(self):
        self.request.audit_doc = audit_doc = fake_audit_doc(user=None)
        self.request.couch_user = Config(username="couch_user")
        with configured_middleware() as ware:
            ware(self.request)
        self.assertEqual(audit_doc.status_code, 200)
        self.assertEqual(audit_doc.user, "couch_user")
        self.assertEqual(audit_doc.save.count, 1)

    def assert_audit(self, request):
        audit_doc = getattr(request, "audit_doc", None)
        self.assertEqual(audit_doc, EXPECTED_AUDIT, "audit expected")

    def assert_no_audit(self, request):
        self.assertFalse(hasattr(request, "audit_doc"), "unexpected audit")


def test_make_view_function():
    func = make_view()
    eq(func.__name__, "the_view")
    eq(func.__module__, "corehq.apps.auditcare.views")


def test_make_view_class():
    func = make_view("ClassView")
    eq(func.__class__.__name__, "ClassView")
    eq(func.__module__, "corehq.apps.auditcare.views")


def test_make_admin_view_function():
    func = make_view("the_view", "django.contrib.admin")
    eq(func.__name__, "the_view")
    eq(func.__module__, "django.contrib.admin")


def test_make_admin_view_class():
    func = make_view("ClassView", "django.contrib.admin")
    eq(func.__class__.__name__, "ClassView")
    eq(func.__module__, "django.contrib.admin")


ARGS = ()  # positional view args are not audited, therefore are empty
KWARGS = {"non": "empty", "and": "audited", "view": "kwargs"}
EXPECTED_AUDIT = Config(user="username", view_kwargs=KWARGS)
Settings = Config(
    AUDIT_MODULES=default_settings.AUDIT_MODULES,
    AUDIT_VIEWS=default_settings.AUDIT_VIEWS,
)


@contextmanager
def configured_middleware(settings=Settings):
    response = Config(status_code=200)
    with patch.object(mod.NavigationEventAudit, "audit_view", fake_audit), \
            patch.object(mod, "settings", settings):
        yield mod.AuditMiddleware(lambda request: response)


def make_view(name="the_view", module="corehq.apps.auditcare.views"):
    is_class = name[0].isupper()
    if is_class:
        view_func = type(name, (), {})()
    else:
        def view_func():
            assert False, "unexpected call"
        view_func.__name__ = name
    view_func.__module__ = module
    return view_func


def fake_audit(request, user, view_func, view_kwargs, extra={}):
    return Config(user=user, view_kwargs=view_kwargs)


def fake_audit_doc(**kwargs):
    def save():
        save.count += 1
    save.count = 0
    return Config(save=save, **kwargs)
