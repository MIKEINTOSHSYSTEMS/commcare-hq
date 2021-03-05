import datetime
from functools import partial
from itertools import chain

from attr import attrib, attrs
from dateutil.parser import parse

from dimagi.utils.parsing import FALSE_STRINGS

from corehq.apps.es import case_search
from corehq.apps.es import cases as case_es

from .core import UserError, serialize_es_case

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 5000
CASE_PROPERTY_PREFIX = 'property.'


def _to_boolean(val):
    return not (val == '' or val.lower() in FALSE_STRINGS)


def _to_int(val, param):
    try:
        return int(val)
    except ValueError:
        raise UserError(f"'{val}' is not a valid value for '{param}'")


def _make_date_filter(date_filter, param):

    def filter_fn(val):
        try:
            # If it's only a date, don't turn it into a datetime
            val = datetime.datetime.strptime(val, '%Y-%m-%d').date()
        except ValueError:
            try:
                val = parse(val)
            except ValueError:
                raise UserError(f"Cannot parse datetime '{val}'")
        return date_filter(**{param: val})

    return filter_fn


def _to_date_filters(field, date_filter):
    return [
        (f'{field}.gt', _make_date_filter(date_filter, 'gt')),
        (f'{field}.gte', _make_date_filter(date_filter, 'gte')),
        (f'{field}.lte', _make_date_filter(date_filter, 'lte')),
        (f'{field}.lt', _make_date_filter(date_filter, 'lt')),
    ]


FILTERS = {
    'external_id': case_search.external_id,
    'case_type': case_es.case_type,
    'owner_id': case_es.owner,
    'case_name': case_es.case_name,
    'closed': lambda val: case_es.is_closed(_to_boolean(val)),
}
FILTERS.update(chain(*[
    _to_date_filters('last_modified', case_es.modified_range),
    _to_date_filters('server_last_modified', case_es.server_modified_range),
    _to_date_filters('date_opened', case_es.opened_range),
    _to_date_filters('date_closed', case_es.closed_range),
]))


@attrs(kw_only=True)
class CaseListParams:
    offset = attrib(converter=partial(_to_int, param='offset'))
    limit = attrib(converter=partial(_to_int, param='limit'))
    metadata_filters = attrib()
    case_property_filters = attrib()

    @classmethod
    def from_querydict(cls, querydict):
        self = CaseListParams(
            offset=querydict.pop('offset', 0),
            limit=querydict.pop('limit', DEFAULT_PAGE_SIZE),
            metadata_filters=[],
            case_property_filters=[],
        )
        for key, val in querydict.items():
            if key.startswith(CASE_PROPERTY_PREFIX):
                self.case_property_filters.append((key, val))
            elif key in FILTERS:
                self.metadata_filters.append((key, val))
            else:
                raise UserError(f"'{key}' is not a valid parameter.")

        return self

    @limit.validator
    def validate_page_size(self, attribute, value):
        if value > MAX_PAGE_SIZE:
            raise UserError(f"You cannot request more than {MAX_PAGE_SIZE} cases per request.")


def get_list(domain, querydict):
    params = CaseListParams.from_querydict(querydict)

    query = (case_search.CaseSearchES()
             .domain(domain)
             .size(params.limit)
             .start(params.offset)
             .sort("@indexed_on"))

    for key, val in params.metadata_filters:
        query = query.filter(FILTERS[key](val))

    for key, val in params.case_property_filters:
        query = query.filter(_get_custom_property_filter(key, val))

    return [serialize_es_case(case) for case in query.run().hits]


def _get_custom_property_filter(key, val):
    prop = key[len(CASE_PROPERTY_PREFIX):]
    if val == "":
        return case_search.case_property_missing(prop)
    return case_search.exact_case_property_text_query(prop, val)
