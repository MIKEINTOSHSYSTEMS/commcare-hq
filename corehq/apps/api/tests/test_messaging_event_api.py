import json
import urllib.parse
from datetime import datetime

from corehq.apps.api.tests.utils import APIResourceTest
from corehq.apps.api.resources.v0_5 import MessagingEventResource
from corehq.apps.sms.models import MessagingEvent, MessagingSubEvent
from corehq.apps.sms.tests.data_generator import create_fake_sms, make_case_rule_sms, make_survey_sms, \
    make_email_event, make_events_for_test
from corehq.apps.users.models import CommCareUser


class TestMessagingEventResource(APIResourceTest):
    resource = MessagingEventResource
    api_name = 'v0.5'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def _create_sms_messages(self, count, randomize, domain=None):
        domain = domain or self.domain.name
        for i in range(count):
            create_fake_sms(domain, randomize=randomize)

    def _serialized_messaging_event(self):
        return {
            "content_type": "sms",
            "date": "2016-01-01T12:00:00",
            "case_id": None,
            "domain": "qwerty",
            "error": None,
            "form": None,
            'messages': [
                {
                    'backend': 'fake-backend-id',
                    'contact': '99912345678',
                    'content': 'test sms text',
                    'date': '2016-01-01T12:00:00',
                    'direction': 'outgoing',
                    'status': 'sent',
                    'type': 'sms'
                }
            ],
            # "id": 1,  # ids are explicitly removed from comparison
            "recipient": {'display': 'unknown', 'id': None, 'type': 'case'},
            "source": {'id': None, 'display': 'sms', 'type': "other"},
            "status": "completed",
        }

    def test_get_list_simple(self):
        self._create_sms_messages(2, randomize=False)
        response = self._assert_auth_get_resource(self.list_endpoint)
        self.assertEqual(response.status_code, 200, response.content)
        data = json.loads(response.content)['objects']
        self.assertEqual(2, len(data))
        for result in data:
            del result['id']  # don't bother comparing ids
            self.assertEqual(self._serialized_messaging_event(), result)

    def test_date_ordering(self):
        self._create_sms_messages(5, randomize=True)
        response = self._assert_auth_get_resource(f'{self.list_endpoint}?order_by=date')
        self.assertEqual(response.status_code, 200, response.content)
        ordered_data = json.loads(response.content)['objects']
        self.assertEqual(5, len(ordered_data))
        dates = [r['date'] for r in ordered_data]
        self.assertEqual(dates, sorted(dates))

        response = self._assert_auth_get_resource(f'{self.list_endpoint}?order_by=-date')
        self.assertEqual(response.status_code, 200, response.content)
        reverse_ordered_data = json.loads(response.content)['objects']
        self.assertEqual(ordered_data, list(reversed(reverse_ordered_data)))

    def test_domain_filter(self):
        self._create_sms_messages(5, randomize=True, domain='different-one')
        response = self._assert_auth_get_resource(f'{self.list_endpoint}?order_by=date')
        self.assertEqual(response.status_code, 200, response.content)
        ordered_data = json.loads(response.content)['objects']
        self.assertEqual(0, len(ordered_data))

    def test_date_filter_lt(self):
        dates = self._setup_for_date_filter_test()
        self._check_date_filtering_response({
            "date.lt": dates[3].isoformat()
        }, [d.isoformat() for d in dates[:3]])

    def test_date_filter_lte(self):
        dates = self._setup_for_date_filter_test()
        self._check_date_filtering_response({
            "date.lte": dates[3].isoformat()
        }, [d.isoformat() for d in dates[:4]])

    def test_date_filter_lte_date(self):
        """`lte` filter with a date (not datetime) should include data
        on that day."""
        dates = self._setup_for_date_filter_test()
        self._check_date_filtering_response({
            "date.lte": str(dates[0].date())
        }, [d.isoformat() for d in dates])

    def test_date_filter_gt(self):
        dates = self._setup_for_date_filter_test()
        self._check_date_filtering_response({
            "date.gt": dates[2].isoformat(),
        }, [d.isoformat() for d in dates[3:]])

    def test_date_filter_gte(self):
        """`gte` filter with a date (not datetime) should include data
        on that day."""
        dates = self._setup_for_date_filter_test()
        self._check_date_filtering_response({
            "date.gte": dates[2].isoformat(),
        }, [d.isoformat() for d in dates[2:]])

    def test_date_filter_gte_date(self):
        dates = self._setup_for_date_filter_test()
        self._check_date_filtering_response({
            "date.gte": str(dates[0].date())
        }, [d.isoformat() for d in dates])

    def _setup_for_date_filter_test(self):
        self._create_sms_messages(5, randomize=True)
        return list(
            MessagingSubEvent.objects.filter(parent__domain=self.domain.name)
            .order_by('date')
            .values_list('date', flat=True)
        )

    def _check_date_filtering_response(self, filters, expected):
        url = f'{self.list_endpoint}?order_by=date&' + urllib.parse.urlencode(filters)
        response = self._assert_auth_get_resource(url)
        self.assertEqual(response.status_code, 200, response.content)
        actual = [event["date"] for event in json.loads(response.content)['objects']]
        self.assertEqual(actual, expected)

    def test_source_filtering(self):
        sources = [
            MessagingEvent.SOURCE_BROADCAST, MessagingEvent.SOURCE_KEYWORD,
            MessagingEvent.SOURCE_REMINDER, MessagingEvent.SOURCE_UNRECOGNIZED,
            MessagingEvent.SOURCE_CASE_RULE
        ]
        for source in sources:
            make_events_for_test(self.domain.name, datetime.utcnow(), source=source)

        url = f'{self.list_endpoint}?order_by=date&source=keyword,reminder'
        response = self._assert_auth_get_resource(url)
        self.assertEqual(response.status_code, 200, response.content)
        actual = {event["source"]["type"] for event in json.loads(response.content)['objects']}
        self.assertEqual(actual, {"keyword", "reminder", "conditional-alert"})

    def test_content_type_filtering(self):
        content_types = [
            MessagingEvent.CONTENT_SMS, MessagingEvent.CONTENT_EMAIL,
            MessagingEvent.CONTENT_API_SMS, MessagingEvent.CONTENT_IVR_SURVEY,
            MessagingEvent.CONTENT_SMS_SURVEY
        ]
        for content_type in content_types:
            make_events_for_test(self.domain.name, datetime.utcnow(), content_type=content_type)

        url = f'{self.list_endpoint}?order_by=date&content_type=ivr-survey,sms'
        response = self._assert_auth_get_resource(url)
        self.assertEqual(response.status_code, 200, response.content)
        actual = {event["content_type"] for event in json.loads(response.content)['objects']}
        self.assertEqual(actual, {"sms", "api-sms", "ivr-survey"})

    def test_status_filtering_error(self):
        make_events_for_test(self.domain.name, datetime.utcnow())
        make_events_for_test(self.domain.name, datetime.utcnow(), status=MessagingEvent.STATUS_ERROR)
        url = f'{self.list_endpoint}?status=error'
        response = self._assert_auth_get_resource(url)
        self.assertEqual(response.status_code, 200, response.content)
        actual = {event["status"] for event in json.loads(response.content)['objects']}
        self.assertEqual(actual, {"error"})

    def test_error_code_filtering(self):
        self._create_sms_messages(2, True)
        e1 = MessagingSubEvent.objects.filter(parent__domain=self.domain.name)[0]
        e1.error_code = MessagingEvent.ERROR_CANNOT_FIND_FORM
        e1.save()
        url = f'{self.list_endpoint}?error_code=CANNOT_FIND_FORM'
        response = self._assert_auth_get_resource(url)
        self.assertEqual(response.status_code, 200, response.content)
        actual = {event["id"] for event in json.loads(response.content)['objects']}
        self.assertEqual(actual, {e1.id})

    def test_case_id_filter(self):
        self._create_sms_messages(2, True)
        e1 = MessagingSubEvent.objects.filter(parent__domain=self.domain.name)[0]
        e1.case_id = "123"
        e1.save()
        url = f'{self.list_endpoint}?case_id=123'
        response = self._assert_auth_get_resource(url)
        self.assertEqual(response.status_code, 200, response.content)
        actual = {event["case_id"] for event in json.loads(response.content)['objects']}
        self.assertEqual(actual, {"123"})

    def test_contact_filter(self):
        user_ids = []
        for i in range(2):
            user = CommCareUser.create(
                self.domain.name, f"user {i}", "123", None, None, email=f"user{i}@email.com"
            )
            user_ids.append(user.get_id)
            self.addCleanup(user.delete, deleted_by=None)
        make_email_event(self.domain.name, "test broadcast", user_ids)
        self._create_sms_messages(1, False)

        self._check_contact_filtering("user0@email.com")
        self._check_contact_filtering("user1@email.com")
        self._check_contact_filtering("99912345678")

    def test_contact_filter_validation(self):
        url = f'{self.list_endpoint}?contact=not-an-email'
        response = self._assert_auth_get_resource(url)
        self.assertEqual(response.status_code, 400, response.content)

    def _check_contact_filtering(self, contact):
        url = f'{self.list_endpoint}?contact={contact}'
        response = self._assert_auth_get_resource(url)
        self.assertEqual(response.status_code, 200, response.content)
        print(json.loads(response.content)['objects'])
        actual = {event["messages"][0]["contact"] for event in json.loads(response.content)['objects']}
        self.assertEqual(actual, {contact})

    def test_case_rule(self):
        rule, event, sms = make_case_rule_sms(self.domain.name, "case rule name", datetime(2016, 1, 1, 12, 0))
        self.addCleanup(rule.delete)
        self.addCleanup(event.delete)  # cascades to subevent
        self.addCleanup(sms.delete)

        expected = {
            "case_id": None,
            "content_type": "sms",
            "date": "2016-01-01T12:00:00",
            "domain": "qwerty",
            "error": None,
            "form": None,
            "messages": [
                {
                    "backend": 'fake-backend-id',
                    "contact": "99912345678",
                    "content": "test sms text",
                    "date": "2016-01-01T12:00:00",
                    "direction": "outgoing",
                    "status": "sent",
                    "type": "sms"
                }
            ],
            "recipient": {
                "display": "unknown",
                "id": "case_id_123",
                "type": "case"
            },
            "source": {
                "display": "case rule name",
                "type": "conditional-alert"
            },
            "status": "in-progress"
        }

        response = self._assert_auth_get_resource(self.list_endpoint)
        self.assertEqual(response.status_code, 200, response.content)
        data = json.loads(response.content)['objects']
        self.assertEqual(1, len(data))
        for result in data:
            del result['id']
            del result['source']['id']
            self.assertEqual(expected, result)

    def test_survey_sms(self):
        rule, xforms_session, event, sms = make_survey_sms(
            self.domain.name, "test sms survey", datetime(2016, 1, 1, 12, 0)
        )
        self.addCleanup(rule.delete)
        self.addCleanup(xforms_session.delete)
        self.addCleanup(event.delete)  # cascades to subevent
        self.addCleanup(sms.delete)

        expected = {
            "case_id": None,
            "content_type": "ivr-survey",
            "date": "2016-01-01T12:00:00",
            "domain": "qwerty",
            "error": None,
            "form": {
                "app_id": "fake_app_id",
                "form_name": "fake form name",
                "form_submission_id": "fake_form_submission_id",
                "form_definition_id": "fake_form_id"
            },
            "messages": [
                {
                    "backend": "fake-backend-id",
                    "contact": "99912345678",
                    "content": "test sms text",
                    "date": "2016-01-01T12:00:00",
                    "direction": "outgoing",
                    "status": "sent",
                    "type": "ivr"
                }
            ],
            "recipient": {
                "display": "unknown",
                "id": "user_id_xyz",
                "type": "mobile-worker"
            },
            "source": {
                "display": "test sms survey",
                "type": "conditional-alert"
            },
            "status": "in-progress"
        }

        response = self._assert_auth_get_resource(self.list_endpoint)
        self.assertEqual(response.status_code, 200, response.content)
        data = json.loads(response.content)['objects']
        self.assertEqual(1, len(data))
        for result in data:
            del result['id']
            del result['source']['id']
            self.assertEqual(expected, result)

    def test_email(self):
        user = CommCareUser.create(self.domain.name, "bob", "123", None, None, email="bob@email.com")
        self.addCleanup(user.delete, deleted_by=None)
        make_email_event(self.domain.name, "test broadcast", [user.get_id])

        expected = {
            "case_id": None,
            "content_type": "email",
            # "date": "2021-06-02T15:08:20.546006",
            "domain": "qwerty",
            "error": None,
            "form": None,
            "messages": [
                {
                    "backend": "email",
                    "contact": "bob@email.com",
                    "content": "Check out the new API.",
                    # "date": "2021-06-02T15:08:20.546006",
                    "direction": "outgoing",
                    "status": "email-delivered",
                    "type": "email"
                }
            ],
            "recipient": {
                "display": "bob",
                "id": user.get_id,
                "type": "mobile-worker"
            },
            "source": {
                "display": "test broadcast",
                "type": "immediate-broadcast"
            },
            "status": "email-delivered"
        }

        response = self._assert_auth_get_resource(self.list_endpoint)
        self.assertEqual(response.status_code, 200, response.content)
        data = json.loads(response.content)['objects']
        self.assertEqual(1, len(data))
        for result in data:
            del result['id']
            del result['source']['id']
            del result['date']
            del result['messages'][0]['date']
            self.assertEqual(expected, result)
