from corehq.apps.export.transforms import case_or_user_id_to_name
from corehq.apps.reports.standard.message_event_display import get_event_display_api, get_sms_status_display_raw
from corehq.apps.sms.models import MessagingEvent, MessagingSubEvent, Email, SMS
from corehq.apps.sms.util import get_backend_name


def serialize_event(event):
    return {
        "id": event.id,
        "content_type": MessagingEvent.CONTENT_TYPE_SLUGS.get(event.content_type, "unknown"),
        "date": event.date.isoformat(),
        "case_id": event.case_id,
        "domain": event.parent.domain,
        "error": _serialize_event_error(event),
        "form": _serialize_event_form(event),
        'messages': _serialize_event_messages(event),
        "recipient": _serialize_event_recipient(event),
        "source": _serialize_event_source(event),
        "status": _serialize_event_status(event),
    }


def _serialize_event_status(event):
    """The status of the event is not tied to the status of individual messages. An event
    may be 'complete' but some or all of the messages may have errored.

    In the case of completed survey events the status is taken from the XFormsSession.
    """
    if event.status == MessagingEvent.STATUS_COMPLETED and event.xforms_session_id:
        return event.xforms_session.status_slug
    return MessagingEvent.STATUS_SLUGS.get(event.status, 'unknown')


def _serialize_event_error(event):
    """Details about the error at the event level. Not related to errors of individual messages."""
    if not event.error_code:
        return None

    return {
        "code": event.error_code,
        "message": MessagingEvent.ERROR_MESSAGES.get(event.error_code, None),
        "message_detail": event.additional_error_text
    }


def _serialize_event_messages(event):
    """The content_types supported here are the only ones used by the MessagingSubEvent
    model. Other content types such as CONTENT_CHAT_SMS are used by the MessagingEvent model.
    """
    if event.content_type == MessagingEvent.CONTENT_EMAIL:
        return _get_messages_for_email(event)

    if event.content_type in (MessagingEvent.CONTENT_SMS, MessagingEvent.CONTENT_SMS_CALLBACK):
        return _get_messages_for_sms(event)

    if event.content_type in (MessagingEvent.CONTENT_SMS_SURVEY, MessagingEvent.CONTENT_IVR_SURVEY):
        return _get_messages_for_survey(event)
    return []


def _serialize_event_recipient(event):
    name = None
    if event.recipient_id:
        name = case_or_user_id_to_name(event.recipient_id, {
            "couch_recipient_doc_type": event.get_recipient_doc_type()
        })
    return {
        "id": event.recipient_id,
        "type": MessagingSubEvent.RECIPIENT_SLUGS.get(event.recipient_type, "unknown"),
        "name": name or "unknown",
    }


def _serialize_event_source(event):
    """This is the 'trigger' for the event e.g. broadcast, conditional-alert etc."""
    parent = event.parent

    return {
        "id": parent.source_id,
        "type": MessagingEvent.SOURCE_SLUGS.get(parent.source, 'unknown'),
        "name": get_event_display_api(parent),
    }


def _serialize_event_form(event):
    if event.content_type not in (MessagingEvent.CONTENT_SMS_SURVEY, MessagingEvent.CONTENT_IVR_SURVEY):
        return None

    submission_id = None
    if event.xforms_session_id:
        submission_id = event.xforms_session.submission_id
    return {
        "app_id": event.app_id,
        "form_definition_id": event.form_unique_id,
        "form_name": event.form_name,
        "form_submission_id": submission_id,
    }


def _get_messages_for_email(event):
    try:
        email = Email.objects.get(messaging_subevent=event.pk)
        content = email.body
        recipient_address = email.recipient_address
    except Email.DoesNotExist:
        content = '-'
        recipient_address = '-'

    return [{
        "date": event.date,
        "type": "email",
        "direction": "outgoing",
        "content": content,
        "status": MessagingEvent.STATUS_SLUGS.get(event.status, 'unknown'),
        "backend": "email",
        "contact": recipient_address
    }]


def _get_messages_for_sms(event):
    messages = SMS.objects.filter(messaging_subevent_id=event.pk)
    return _get_message_dicts_for_sms(event, messages, "sms")


def _get_messages_for_survey(event):
    if not event.xforms_session_id:
        return []

    xforms_session = event.xforms_session
    if not xforms_session:
        return []

    messages = SMS.objects.filter(xforms_session_couch_id=xforms_session.couch_id)
    type_ = "ivr" if event.content_type == MessagingEvent.CONTENT_IVR_SURVEY else "sms"
    return _get_message_dicts_for_sms(event, messages, type_)


def _get_message_dicts_for_sms(event, messages, type_):
    message_dicts = []
    for sms in messages:
        error_message = None
        if event.status != MessagingEvent.STATUS_ERROR:
            status, error_message = get_sms_status_display_raw(sms)
        else:
            status = MessagingEvent.STATUS_SLUGS.get(event.status, "unknown")

        message_data = {
            "date": sms.date,
            "type": type_,
            "direction": SMS.DIRECTION_SLUGS.get(sms.direction, "unknown"),
            "content": sms.text,
            "status": status,
            "backend": get_backend_name(sms.backend_id) or sms.backend_id,
            "contact": sms.phone_number
        }
        if error_message:
            message_data["error_message"] = error_message
        message_dicts.append(message_data)
    return message_dicts
