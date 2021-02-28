import random
import string
from datetime import datetime
from uuid import uuid4

from django.test import TestCase

from casexml.apps.case.models import CommCareCase
from casexml.apps.case.sharedmodels import CommCareCaseIndex

from corehq.apps.accounting.models import SoftwarePlanEdition
from corehq.apps.accounting.tests.utils import DomainSubscriptionMixin
from corehq.apps.accounting.utils import clear_plan_version_cache
from corehq.apps.data_dictionary.models import CaseProperty, CaseType
from corehq.apps.domain.shortcuts import create_domain

from ..const import FHIR_VERSION_4_0_1
from ..models import (
    FHIRResourceProperty,
    FHIRResourceType,
    get_case_trigger_info,
)
from ..repeater_helpers import get_info_resources_list

DOMAIN = ''.join([random.choice(string.ascii_lowercase) for __ in range(20)])


class TestGetInfoResourcesListOneCase(TestCase, DomainSubscriptionMixin):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain_obj = create_domain(DOMAIN)
        cls.setup_subscription(DOMAIN, SoftwarePlanEdition.PRO)

        cls.case_type = CaseType.objects.create(
            domain=DOMAIN, name='person')
        name = CaseProperty.objects.create(
            case_type=cls.case_type, name='name')

        resource_type = FHIRResourceType.objects.create(
            domain=DOMAIN, case_type=cls.case_type, name='Patient')
        FHIRResourceProperty.objects.create(
            resource_type=resource_type,
            case_property=name,
            jsonpath='$.name[0].text',
        )

    @classmethod
    def tearDownClass(cls):
        cls.case_type.delete()
        cls.teardown_subscriptions()
        cls.domain_obj.delete()
        clear_plan_version_cache()
        super().tearDownClass()

    def setUp(self):
        now = datetime.utcnow()
        self.case_id = str(uuid4())
        self.case = CommCareCase(
            _id=self.case_id,
            domain=DOMAIN,
            type='person',
            name='Ted',
            owner_id=str(uuid4()),
            modified_on=now,
            server_modified_on=now,
        )
        self.case.save()

    def tearDown(self):
        self.case.delete()

    def test_get_info_resources_list(self):
        case_trigger_infos = [get_case_trigger_info(self.case)]
        [(info, resource)] = get_info_resources_list(
            case_trigger_infos,
            FHIR_VERSION_4_0_1,
        )
        self.assertEqual(resource, {
            'id': self.case_id,
            'name': [{'text': 'Ted'}],
            'resourceType': 'Patient'
        })


class TestGetInfoResourcesListSubCases(TestCase, DomainSubscriptionMixin):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain_obj = create_domain(DOMAIN)
        cls.setup_subscription(DOMAIN, SoftwarePlanEdition.PRO)

        cls.person_case_type = CaseType.objects.create(
            domain=DOMAIN, name='person')
        name = CaseProperty.objects.create(
            case_type=cls.person_case_type, name='name')

        resource_type_for_person = FHIRResourceType.objects.create(
            domain=DOMAIN, case_type=cls.person_case_type, name='Patient')
        FHIRResourceProperty.objects.create(
            resource_type=resource_type_for_person,
            case_property=name,
            jsonpath='$.name[0].text',
        )
        FHIRResourceProperty.objects.create(
            resource_type=resource_type_for_person,
            value_source_config={
                'subcase_value_source': {
                    'case_property': 'given_names',
                    # Use counter1 to skip the name set by the parent case
                    'jsonpath': '$.name[{counter1}].given[0]',
                },
                'case_types': ['person_name'],
            }
        )
        FHIRResourceProperty.objects.create(
            resource_type=resource_type_for_person,
            value_source_config={
                'subcase_value_source': {
                    'case_property': 'family_name',
                    'jsonpath': '$.name[{counter1}].family',
                },
                'case_types': ['person_name'],
            }
        )

    @classmethod
    def tearDownClass(cls):
        cls.person_case_type.delete()
        cls.teardown_subscriptions()
        cls.domain_obj.delete()
        clear_plan_version_cache()
        super().tearDownClass()

    def setUp(self):
        now = datetime.utcnow()
        self.parent_case_id = str(uuid4())
        self.parent_case = CommCareCase(
            _id=self.parent_case_id,
            domain=DOMAIN,
            type='person',
            name='Ted',
            owner_id=str(uuid4()),
            modified_on=now,
            server_modified_on=now,
        )
        self.parent_case.save()

        self.child_case_1 = CommCareCase(
            case_id='111111111',
            domain=DOMAIN,
            type='person_name',
            name='Theodore',
            given_names='Theodore John',
            family_name='Kaczynski',
            indices=[CommCareCaseIndex(
                identifier='parent',
                referenced_type='person',
                referenced_id=self.parent_case_id,
            )],
            owner_id=str(uuid4()),
            modified_on=now,
            server_modified_on=now,
        )
        self.child_case_1.save()
        self.child_case_2 = CommCareCase(
            case_id='222222222',
            domain=DOMAIN,
            type='person_name',
            name='Unabomber',
            given_names='Unabomber',
            indices=[CommCareCaseIndex(
                identifier='parent',
                referenced_type='person',
                referenced_id=self.parent_case_id,
            )],
            owner_id=str(uuid4()),
            modified_on=now,
            server_modified_on=now,
        )
        self.child_case_2.save()

    def tearDown(self):
        self.child_case_1.delete()
        self.child_case_2.delete()
        self.parent_case.delete()

    def test_get_info_resources_list(self):
        case_trigger_infos = [get_case_trigger_info(self.parent_case)]
        [(info, resource)] = get_info_resources_list(
            case_trigger_infos,
            FHIR_VERSION_4_0_1,
        )
        self.assertEqual(resource, {
            'id': self.parent_case_id,
            'name': [
                {'text': 'Ted'},
                {'given': ['Theodore John'], 'family': 'Kaczynski'},
                {'given': ['Unabomber']},
            ],
            'resourceType': 'Patient',
        })
