from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _

from celery.task import task

from corehq.apps.consumer_user.models import (
    ConsumerUserCaseRelationship,
    ConsumerUserInvitation,
)
from corehq.apps.hqcase.utils import update_case
from corehq.apps.hqwebapp.tasks import send_html_email_async
from corehq.util.view_utils import absolute_reverse

from .const import (
    CONSUMER_INVITATION_ACCEPTED,
    CONSUMER_INVITATION_SENT,
    CONSUMER_INVITATION_STATUS,
)


@task
def create_new_consumer_user_invitation(
    domain, invitation_case_id, demographic_case_id, closed, status, opened_by, email
):
    invitation = ConsumerUserInvitation.objects.filter(
        case_id=invitation_case_id,
        domain=domain,
        demographic_case_id=demographic_case_id,
        active=True,
    ).last()

    # Set invitation inactive when the invitation case is closed, and there is an invitation
    if closed:
        if invitation:
            invitation.make_inactive()
        return

    # If the invitation is already "sent" or "accepted" and this is the same email address, do nothing
    elif (
        invitation and email == invitation.email
        and status in [CONSUMER_INVITATION_SENT, CONSUMER_INVITATION_ACCEPTED]
    ):
        return

    # Otherwise, close this invitation
    elif invitation:
        invitation.make_inactive()
        if ConsumerUserCaseRelationship.objects.filter(case_id=demographic_case_id, domain=domain).exists():
            # There is already a relationship with this case_id, so we can't invite someone new
            return

    invitation = ConsumerUserInvitation.objects.create(
        case_id=invitation_case_id,
        domain=domain,
        demographic_case_id=demographic_case_id,
        invited_by=opened_by,
        email=email,
    )
    email_context = {
        'link':
            absolute_reverse(
                'consumer_user:consumer_user_register',
                kwargs={'invitation': invitation.signature()},
            ),
    }
    send_html_email_async.delay(
        _('Beneficiary Registration'),
        email,
        render_to_string('consumer_user/email/registration_email.html', email_context),
        text_content=render_to_string('consumer_user/email/registration_email.txt', email_context)
    )
    update_case(domain, invitation_case_id, {CONSUMER_INVITATION_STATUS: CONSUMER_INVITATION_SENT})
