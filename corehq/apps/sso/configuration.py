import datetime

from django.conf import settings
from onelogin.saml2.constants import OneLogin_Saml2_Constants

from dimagi.utils.web import get_url_base
from corehq.apps.sso.utils import url_helpers


def get_saml2_config(identity_provider):
    sp_settings = {
        "entityId": url_helpers.get_saml_entity_id(identity_provider),
        "assertionConsumerService": {
            "url": url_helpers.get_saml_acs_url(identity_provider),
            "binding": OneLogin_Saml2_Constants.BINDING_HTTP_POST,
        },
        "singleLogoutService": {
            "url": url_helpers.get_saml_sls_url(identity_provider),
            "binding": OneLogin_Saml2_Constants.BINDING_HTTP_REDIRECT,
        },
        "attributeConsumingService": {
            "serviceName": "CommCare HQ",
            "serviceDescription": "SSO for CommCare HQ",
            "requestedAttributes": [
                {
                    "name": "emailAddress",
                    "isRequired": True,
                    "nameFormat": OneLogin_Saml2_Constants.NAMEID_EMAIL_ADDRESS,
                    "friendlyName": "Email Address",
                    "attributeValue": ["email@example.com"],
                },
            ],
        },
        "NameIDFormat": OneLogin_Saml2_Constants.NAMEID_EMAIL_ADDRESS,
        "x509cert": identity_provider.sp_cert_public,
        "privateKey": identity_provider.sp_cert_private,
    }

    if identity_provider.sp_rollover_cert_public:
        sp_settings['x509certNew'] = identity_provider.sp_rollover_cert_public

    saml_config = {
        "strict": True,
        "debug": settings.SAML2_DEBUG,
        "sp": sp_settings,
        "idp": {
            "entityId": identity_provider.entity_id,
            "singleSignOnService": {
                "url": identity_provider.login_url,
                "binding": OneLogin_Saml2_Constants.BINDING_HTTP_REDIRECT,
            },
            "singleLogoutService": {
                "url": identity_provider.logout_url,
                "binding": OneLogin_Saml2_Constants.BINDING_HTTP_REDIRECT,
            },
            "x509cert": identity_provider.idp_cert_public,
        },
    }

    saml_config.update(_get_advanced_saml2_settings())
    return saml_config


def _get_advanced_saml2_settings():
    metadata_valid_until = datetime.datetime.utcnow() + datetime.timedelta(days=3)
    return {
        "security": {
            "nameIdEncrypted": True,
            "authnRequestsSigned": True,
            "logoutRequestSigned": True,
            "logoutResponseSigned": True,
            "signMetadata": False,

            # Signing/encrypting assertions and responses is a Premium feature offered
            # by Azure AD (see: Token encryption) and is not available by default.
            # Turning this off for now as HTTPS makes the handshake secure
            # todo to discuss to make this a configurable parameter
            "wantAssertionsSigned": True,
            "wantMessagesSigned": False,
            "wantAssertionsEncrypted": True,

            "wantNameId": True,
            "wantNameIdEncrypted": False,  # Azure will not accept if True
            "failOnAuthnContextMismatch": True,  # very important
            "signatureAlgorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
            "digestAlgorithm": "http://www.w3.org/2001/04/xmlenc#sha256",
            "metadataValidUntil": metadata_valid_until.isoformat(),
        },
        "contactPerson": {
            "technical": {
                "givenName": "Accounts Team",
                "emailAddress": settings.ACCOUNTS_EMAIL,
            },
            "support": {
                "givenName": "Support Team",
                "emailAddress": settings.SUPPORT_EMAIL,
            },
        },
        "organization": {
            "en-US": {
                "name": "commcare_hq",
                "displayname": "CommCare HQ",
                "url": get_url_base(),
            },
        },
    }
