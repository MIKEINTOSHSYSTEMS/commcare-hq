import datetime

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.translation import ugettext as _
from django.utils.html import format_html

from corehq.const import USER_DATE_FORMAT
from dimagi.utils.web import get_site_domain


def get_success_message_for_trusted_idp(idp, domain_obj):
    """
    Small utility to return a success message that a TrustedIdentityProvider
    relationship was established between an Identity Provider and a Domain.

    :param idp: IdentityProvider
    :param domain_obj: Domain object
    :return: String (the final message)
    """
    return format_html(
        _('{idp} is now trusted as an identity provider for users '
          'who are members of the project space "{domain}". '
          '<a href="{learn_more}">Learn More</a>'),
        idp=idp.name,
        domain=domain_obj.name,
        learn_more='#',  # todo include learn more link
    )


def render_multiple_strings(context, *templates):
    """
    Convenience utility that renders multiple templates with the same context.

    :param context: The context (dict) used to render all `*templates`.
    :param *templates: One or more template names (strings) to be rendered.
    :return: Generator of strings -- rendered text of each provided template.
    """
    return (render_to_string(template, context) for template in templates)


def get_idp_cert_expiration_email(idp):
    """
    Utility to generate metadata and render messages for an IdP certificate
    expiration reminder email.

    :param idp: IdentityProvider
    :return: Dict (parameters for sending email)
    """

    today = datetime.datetime.utcnow().date()
    exp_date = idp.date_idp_cert_expiration.date()
    num_days_left = (exp_date - today).days
    if num_days_left == 0:
        expires_on = _("today!")
    elif num_days_left == 1:
        expires_on = _("tomorrow!")
    else:
        expires_on = _(f"on {exp_date:{USER_DATE_FORMAT}}.")

    context = {
        "idp_name": idp.name,
        "expires_on": expires_on,
        "contact_email": settings.ACCOUNTS_EMAIL,
        "base_url": get_site_domain(),
    }
    subject = _(
        "CommCare Alert: Certificate for Identity Provider %(idp_name)s "
        "expires %(expires_on)s"
    ) % context
    body_html, body_txt = render_multiple_strings(
        context,
        "sso/email/idp_cert_expiring_reminder.html",
        "sso/email/idp_cert_expiring_reminder.txt",
    )
    message = {
        "subject": subject,
        "from": _(f"Dimagi CommCare Accounts <{settings.ACCOUNTS_EMAIL}>"),
        "to": idp.owner.enterprise_admin_emails,
        "bcc": [settings.ACCOUNTS_EMAIL],
        "html": body_html,
        "plaintext": body_txt,
    }
    if idp.owner.dimagi_contact:
        message["bcc"].append(idp.owner.dimagi_contact)
    return message
