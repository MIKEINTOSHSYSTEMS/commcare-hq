import inspect

import graphviz
from testil import eq

from corehq.apps.app_manager.app_schemas.workflow_visualization import generate_app_workflow_diagram_source
from corehq.apps.app_manager.const import (
    WORKFLOW_FORM,
    WORKFLOW_ROOT,
    WORKFLOW_MODULE,
    WORKFLOW_PREVIOUS, WORKFLOW_PARENT_MODULE
)
from corehq.apps.app_manager.models import FormLink
from corehq.apps.app_manager.tests.app_factory import AppFactory
from corehq.apps.app_manager.tests.util import patch_get_xform_resource_overrides


@patch_get_xform_resource_overrides()
def test_workflow_diagram_child_module_form_links():
    factory = AppFactory(build_version='2.9.0')
    m0, m0f0 = factory.new_basic_module('enroll child', 'child')
    factory.form_opens_case(m0f0)

    m1, m1f0 = factory.new_basic_module('child visit', 'child')
    factory.form_requires_case(m1f0)
    factory.form_opens_case(m1f0, case_type='visit', is_subcase=True)

    m2, m2f0 = factory.new_advanced_module('visit history', 'visit', parent_module=m1)
    factory.form_requires_case(m2f0, 'child')
    factory.form_requires_case(m2f0, 'visit', parent_case_type='child')

    m0f0.post_form_workflow = WORKFLOW_FORM
    m0f0.form_links = [
        FormLink(xpath="true()", form_id=m1f0.unique_id),
    ]

    m1f0.post_form_workflow = WORKFLOW_FORM
    m1f0.form_links = [
        FormLink(xpath="(today() - dob) &lt; 7", form_id=m2f0.unique_id),
    ]
    m1f0.post_form_workflow_fallback = WORKFLOW_MODULE

    source = generate_app_workflow_diagram_source(factory.app)
    eq(_normalize(source), inspect.cleandoc("""
    digraph "Untitled Application" {
        graph [rankdir=LR]
        root [label=Root]
        start [label=Start]
        root -> start
        start -> m0
        start -> m1
        {
            rank=same
            m0 [label="enroll child module [en] "]
            m1 [label="child visit module [en] "]
        }
        m0 -> "m0-f0"
        "m1.case_id" -> "m1-f0"
        "m1.case_id" -> m2
        {
            rank=same
            "m0-f0" [label="enroll child form 0 [en] "]
            "m1-f0" [label="child visit form 0 [en] "]
            m2 [label="visit history module [en] "]
        }
        "m1.case_id.m2.case_id_load_visit_0" -> "m2-f0"
        {
            rank=same
            "m2-f0" [label="visit history form 0 [en] "]
        }
        "m0-f0" -> "m0-f0_form_entry"
        "m1-f0" -> "m1-f0_form_entry"
        {
            rank=same
            "m0-f0_form_entry" [label="enroll child form 0 [en] " shape=box]
            "m1-f0_form_entry" [label="child visit form 0 [en] " shape=box]
        }
        "m2-f0" -> "m2-f0_form_entry"
        {
            rank=same
            "m2-f0_form_entry" [label="visit history form 0 [en] " shape=box]
        }
        "m1.case_id" [label="Select 'child' case" shape=folder]
        "m1.case_id.m2.case_id_load_visit_0" [label="Select 'visit' case" shape=folder]
        "m0-f0_form_entry" -> "m1-f0_form_entry" [label="true()" color=grey]
        m1 -> "m1.case_id"
        "m1-f0_form_entry" -> "m2-f0_form_entry" [label="(today() - dob) &lt; 7" color=grey]
        "m1-f0_form_entry" -> m1 [label="not((today() - dob) &lt; 7)" color=grey constraint=false]
        m2 -> "m1.case_id.m2.case_id_load_visit_0"
    }
    """))


@patch_get_xform_resource_overrides()
def test_workflow_diagram_post_form_workflow_root():
    app = _build_workflow_app(WORKFLOW_ROOT)
    source = generate_app_workflow_diagram_source(app)
    eq(_normalize(source), inspect.cleandoc("""
    digraph "Untitled Application" {
        graph [rankdir=LR]
        root [label=Root]
        start [label=Start]
        root -> start
        start -> m0
        {
            rank=same
            m0 [label="m0 module [en] "]
        }
        m0 -> "m0-f0"
        m0 -> m1
        {
            rank=same
            "m0-f0" [label="m0 form 0 [en] "]
            m1 [label="m1 module [en] "]
        }
        m1 -> "m1-f0"
        {
            rank=same
            "m1-f0" [label="m1 form 0 [en] "]
        }
        "m0-f0" -> "m0-f0_form_entry"
        {
            rank=same
            "m0-f0_form_entry" [label="m0 form 0 [en] " shape=box]
        }
        "m1-f0" -> "m1-f0_form_entry"
        {
            rank=same
            "m1-f0_form_entry" [label="m1 form 0 [en] " shape=box]
        }
        "m0-f0_form_entry" -> start [color=grey constraint=false]
        "m1-f0_form_entry" -> start [color=grey constraint=false]
    }
    """))


@patch_get_xform_resource_overrides()
def test_workflow_diagram_post_form_workflow_module():
    app = _build_workflow_app(WORKFLOW_MODULE)
    source = generate_app_workflow_diagram_source(app)
    eq(_normalize(source), inspect.cleandoc("""
    digraph "Untitled Application" {
        graph [rankdir=LR]
        root [label=Root]
        start [label=Start]
        root -> start
        start -> m0
        {
            rank=same
            m0 [label="m0 module [en] "]
        }
        m0 -> "m0-f0"
        m0 -> m1
        {
            rank=same
            "m0-f0" [label="m0 form 0 [en] "]
            m1 [label="m1 module [en] "]
        }
        m1 -> "m1-f0"
        {
            rank=same
            "m1-f0" [label="m1 form 0 [en] "]
        }
        "m0-f0" -> "m0-f0_form_entry"
        {
            rank=same
            "m0-f0_form_entry" [label="m0 form 0 [en] " shape=box]
        }
        "m1-f0" -> "m1-f0_form_entry"
        {
            rank=same
            "m1-f0_form_entry" [label="m1 form 0 [en] " shape=box]
        }
        "m0-f0_form_entry" -> m0 [color=grey constraint=false]
        "m1-f0_form_entry" -> m1 [color=grey constraint=false]
    }
    """))


@patch_get_xform_resource_overrides()
def test_workflow_diagram_post_form_workflow_previous():
    app = _build_workflow_app(WORKFLOW_PREVIOUS)
    source = generate_app_workflow_diagram_source(app)
    eq(_normalize(source), inspect.cleandoc("""
    digraph "Untitled Application" {
        graph [rankdir=LR]
        root [label=Root]
        start [label=Start]
        root -> start
        start -> m0
        {
            rank=same
            m0 [label="m0 module [en] "]
        }
        m0 -> "m0-f0"
        m0 -> m1
        {
            rank=same
            "m0-f0" [label="m0 form 0 [en] "]
            m1 [label="m1 module [en] "]
        }
        m1 -> "m1-f0"
        {
            rank=same
            "m1-f0" [label="m1 form 0 [en] "]
        }
        "m0-f0" -> "m0-f0_form_entry"
        {
            rank=same
            "m0-f0_form_entry" [label="m0 form 0 [en] " shape=box]
        }
        "m1-f0" -> "m1-f0_form_entry"
        {
            rank=same
            "m1-f0_form_entry" [label="m1 form 0 [en] " shape=box]
        }
        "m0-f0_form_entry" -> m0 [color=grey constraint=false]
        "m1-f0_form_entry" -> m1 [color=grey constraint=false]
    }"""))


@patch_get_xform_resource_overrides()
def test_workflow_diagram_post_form_workflow_parent():
    factory = AppFactory(build_version='2.9.0')

    m1, m1f0 = factory.new_basic_module('child visit', 'child')
    factory.form_requires_case(m1f0)

    m2, m2f0 = factory.new_advanced_module('visit history', 'visit', parent_module=m1)
    factory.form_requires_case(m2f0, 'child')
    factory.form_requires_case(m2f0, 'visit', parent_case_type='child')

    m2f0.post_form_workflow = WORKFLOW_PARENT_MODULE
    source = generate_app_workflow_diagram_source(factory.app)
    eq(_normalize(source), inspect.cleandoc("""
    digraph "Untitled Application" {
        graph [rankdir=LR]
        root [label=Root]
        start [label=Start]
        root -> start
        start -> m0
        {
            rank=same
            m0 [label="child visit module [en] "]
        }
        "m0.case_id" -> "m0-f0"
        "m0.case_id" -> m1
        {
            rank=same
            "m0-f0" [label="child visit form 0 [en] "]
            m1 [label="visit history module [en] "]
        }
        "m0.case_id.m1.case_id_load_visit_0" -> "m1-f0"
        {
            rank=same
            "m1-f0" [label="visit history form 0 [en] "]
        }
        "m0-f0" -> "m0-f0_form_entry"
        {
            rank=same
            "m0-f0_form_entry" [label="child visit form 0 [en] " shape=box]
        }
        "m1-f0" -> "m1-f0_form_entry"
        {
            rank=same
            "m1-f0_form_entry" [label="visit history form 0 [en] " shape=box]
        }
        "m0.case_id" [label="Select 'child' case" shape=folder]
        "m0.case_id.m1.case_id_load_visit_0" [label="Select 'visit' case" shape=folder]
        m0 -> "m0.case_id"
        m1 -> "m0.case_id.m1.case_id_load_visit_0"
        "m1-f0_form_entry" -> m0 [color=grey constraint=false]
    }
    """))


@patch_get_xform_resource_overrides()
def test_workflow_diagram_module_case_list():
    factory = AppFactory(build_version='2.9.0')
    m0, m0f0 = factory.new_basic_module('person', 'person')
    factory.form_opens_case(m0f0)
    m0.case_list.show = True
    m0.case_list.label = {"en": "Al People"}
    source = generate_app_workflow_diagram_source(factory.app)
    eq(_normalize(source), inspect.cleandoc("""
    digraph "Untitled Application" {
        graph [rankdir=LR]
        root [label=Root]
        start [label=Start]
        root -> start
        start -> m0
        start -> "m0-case-list"
        {
            rank=same
            m0 [label="person module [en] "]
            "m0-case-list" [label="person module [en]  Case List"]
        }
        m0 -> "m0-f0"
        {
            rank=same
            "m0-f0" [label="person form 0 [en] "]
        }
        "m0-f0" -> "m0-f0_form_entry"
        {
            rank=same
            "m0-f0_form_entry" [label="person form 0 [en] " shape=box]
        }
        "case_list_id.case_id" [label="Select 'person' case" shape=folder]
        "m0-case-list" -> "case_list_id.case_id"
    }
    """))


@patch_get_xform_resource_overrides()
def test_workflow_diagram_case_list_form():
    factory = AppFactory(build_version='2.9.0')
    m0, m0f0 = factory.new_basic_module("register", "case")
    factory.form_opens_case(m0f0, "case")

    m1, m1f0 = factory.new_basic_module("followup", "case", case_list_form=m0f0)
    factory.form_requires_case(m1f0)
    # m1f1 = factory.new_form(m1)
    # factory.form_opens_case(m1f1, "case")
    source = generate_app_workflow_diagram_source(factory.app)
    eq(_normalize(source), inspect.cleandoc("""
    digraph "Untitled Application" {
        graph [rankdir=LR]
        root [label=Root]
        start [label=Start]
        root -> start
        start -> m0
        start -> m1
        {
            rank=same
            m0 [label="register module [en] "]
            m1 [label="followup module [en] "]
        }
        m0 -> "m0-f0"
        "m1.case_id" -> "m1-f0"
        {
            rank=same
            "m0-f0" [label="register form 0 [en] "]
            "m1-f0" [label="followup form 0 [en] "]
        }
        "m0-f0" -> "m0-f0_form_entry"
        "m1-f0" -> "m1-f0_form_entry"
        {
            rank=same
            "m0-f0_form_entry" [label="register form 0 [en] " shape=box]
            "m1-f0_form_entry" [label="followup form 0 [en] " shape=box]
        }
        "m1.case_id" [label="Select 'case' case" shape=folder]
        "m0-f0_form_entry" -> "m1.case_id" [label="Case Created" color=grey constraint=false]
        "m0-f0_form_entry" -> m1 [label="Case Not Created" color=grey constraint=false]
        m1 -> "m1.case_id"
        "m1.case_id" -> "m0-f0_form_entry" [label="" color=grey constraint=false]
    }"""))


# TODO: module.put_in_root

def _build_workflow_app(mode):
    factory = AppFactory(build_version='2.9.0')
    m0, m0f0 = factory.new_basic_module('m0', '')
    factory.new_basic_module('m1', 'patient', parent_module=m0)

    for module in factory.app.get_modules():
        for form in module.get_forms():
            form.post_form_workflow = mode

    return factory.app


def _normalize(source):
    return source.replace("\t", "    ")
