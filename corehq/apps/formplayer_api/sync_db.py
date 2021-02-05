from corehq.apps.formplayer_api.exceptions import FormplayerResponseException
from corehq.apps.formplayer_api.smsforms.api import _post_data
from corehq.apps.users.models import CouchUser
from corehq.toggles import FORMPLAYER_USE_LIVEQUERY


def sync_db(domain, username, restore_as=None):
    """Call Formplayer API to force a sync for a user."""
    user = CouchUser.get_by_username(username)
    assert user.is_member_of(domain, allow_mirroring=True)
    user_id = user.user_id
    use_livequery = FORMPLAYER_USE_LIVEQUERY.enabled(domain)
    data = {
        'action': 'sync-db',
        'username': username,
        'domain': domain,
        'restoreAs': restore_as,
        'useLiveQuery': use_livequery,
    }
    response_json = _post_data(data, user_id)
    if not response_json.get("status") == "accepted":
        raise FormplayerResponseException(response_json)
