import logging
from collections import namedtuple

from django.db import IntegrityError
from django.http.response import Http404

from dimagi.utils.chunked import chunked

from corehq.apps.app_manager.const import AMPLIFIES_NOT_SET
from corehq.apps.app_manager.dbaccessors import get_app
from corehq.apps.data_analytics.const import AMPLIFY_COUCH_TO_SQL_MAP, NOT_SET
from corehq.apps.data_analytics.esaccessors import (
    get_app_submission_breakdown_es,
)
from corehq.apps.data_analytics.models import MALTRow
from corehq.apps.domain.models import Domain
from corehq.apps.users.dbaccessors import get_all_user_rows
from corehq.apps.users.models import CouchUser
from corehq.const import MISSING_APP_ID
from corehq.util.quickcache import quickcache

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DEFAULT_MINIMUM_USE_THRESHOLD = 15
DEFAULT_EXPERIENCED_THRESHOLD = 3

MaltAppData = namedtuple('MaltAppData', 'wam pam use_threshold experienced_threshold is_app_deleted')


def generate_malt(monthspans, domains=None):
    """
    Populates MALTRow SQL table with app submission data for a given list of months
    :param monthspans: list of DateSpan objects
    :param domains: list of domain ids
    """
    domains = domains or Domain.get_all()
    for domain in domains:
        if isinstance(domain, str):
            domain = Domain.get_by_name(domain)
            if not domain:
                continue

        for monthspan in monthspans:
            logger.info(f"Building MALT for {domain.name} for {monthspan}")
            all_users = get_all_user_rows(domain.name, include_inactive=False, include_docs=True)
            for users in chunked(all_users, 1000):
                users_by_id = {user['id']: CouchUser.wrap_correctly(user['doc']) for user in users}
                malt_rows_to_save = _get_malt_row_dicts(domain.name, monthspan, users_by_id)
                if malt_rows_to_save:
                    _save_to_db(malt_rows_to_save, domain._id)


@quickcache(['domain', 'app_id'])
def _get_malt_app_data(domain, app_id):
    default_app_data = MaltAppData(
        AMPLIFIES_NOT_SET, AMPLIFIES_NOT_SET, DEFAULT_MINIMUM_USE_THRESHOLD, DEFAULT_EXPERIENCED_THRESHOLD, False
    )
    if not app_id:
        return default_app_data
    try:
        app = get_app(domain, app_id)
    except Http404:
        logger.debug("App not found %s" % app_id)
        return default_app_data

    return MaltAppData(getattr(app, 'amplifies_workers', AMPLIFIES_NOT_SET),
                       getattr(app, 'amplifies_project', AMPLIFIES_NOT_SET),
                       getattr(app, 'minimum_use_threshold', DEFAULT_MINIMUM_USE_THRESHOLD),
                       getattr(app, 'experienced_threshold', DEFAULT_EXPERIENCED_THRESHOLD),
                       app.is_deleted())


def _build_malt_row_dict(app_row, domain_name, user, monthspan):
    app_data = _get_malt_app_data(domain_name, app_row.app_id)

    return {
        'month': monthspan.startdate,
        'user_id': user._id,
        'username': user.username,
        'email': user.email,
        'user_type': user.doc_type,
        'domain_name': domain_name,
        'num_of_forms': app_row.doc_count,
        'app_id': app_row.app_id or MISSING_APP_ID,
        'device_id': app_row.device_id,
        'wam': AMPLIFY_COUCH_TO_SQL_MAP.get(app_data.wam, NOT_SET),
        'pam': AMPLIFY_COUCH_TO_SQL_MAP.get(app_data.pam, NOT_SET),
        'use_threshold': app_data.use_threshold,
        'experienced_threshold': app_data.experienced_threshold,
        'is_app_deleted': app_data.is_app_deleted,
    }


def _get_malt_row_dicts(domain_name, monthspan, users_by_id):
    """
    Includes expensive elasticsearch query
    """
    malt_row_dicts = []
    app_rows = get_app_submission_breakdown_es(domain_name, monthspan, list(users_by_id))
    for app_row in app_rows:
        user = users_by_id[app_row.user_id]
        malt_row_dict = _build_malt_row_dict(app_row, domain_name, user, monthspan)
        malt_row_dicts.append(malt_row_dict)

    return malt_row_dicts


def _save_to_db(malt_rows_to_save, domain_id):
    try:
        MALTRow.objects.bulk_create(
            [MALTRow(**malt_dict) for malt_dict in malt_rows_to_save]
        )
    except IntegrityError:
        # no update_or_create in django-1.6
        for malt_dict in malt_rows_to_save:
            _update_or_create(malt_dict)
    except Exception as ex:
        logger.error("Failed to insert rows for domain with id {id}. Exception is {ex}".format(
                     id=domain_id, ex=str(ex)), exc_info=True)


def _update_or_create(malt_dict):
    try:
        # try update
        unique_field_dict = {k: v
                             for (k, v) in malt_dict.items()
                             if k in MALTRow.get_unique_fields()}
        prev_obj = MALTRow.objects.get(**unique_field_dict)
        for k, v in malt_dict.items():
            setattr(prev_obj, k, v)
        prev_obj.save()
    except MALTRow.DoesNotExist:
        # create
        try:
            MALTRow(**malt_dict).save()
        except Exception as ex:
            logger.error("Failed to insert malt-row {}. Exception is {}".format(
                str(malt_dict),
                str(ex)
            ), exc_info=True)
    except Exception as ex:
        logger.error("Failed to insert malt-row {}. Exception is {}".format(
            str(malt_dict),
            str(ex)
        ), exc_info=True)
