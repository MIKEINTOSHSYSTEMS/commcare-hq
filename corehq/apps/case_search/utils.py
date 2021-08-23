import re
from collections import defaultdict

from django.utils.functional import cached_property
from django.utils.translation import ugettext as _

from casexml.apps.case.models import CommCareCase

from corehq.apps.app_manager.dbaccessors import get_app_cached
from corehq.apps.app_manager.util import module_offers_search
from corehq.apps.case_search.const import CASE_SEARCH_MAX_RESULTS
from corehq.apps.case_search.filter_dsl import (
    CaseFilterError,
    build_filter_from_xpath,
)
from corehq.apps.case_search.models import (
    CASE_SEARCH_BLACKLISTED_OWNER_ID_KEY,
    CASE_SEARCH_XPATH_QUERY_KEY,
    SEARCH_QUERY_CUSTOM_VALUE,
    UNSEARCHABLE_KEYS,
    CaseSearchConfig,
    FuzzyProperties,
)
from corehq.apps.es import filters, queries
from corehq.apps.es.case_search import (
    CaseSearchES,
    case_property_missing,
    case_property_query,
    case_property_range_query,
    flatten_result,
)


class CaseSearchCriteria(object):
    """Compiles the case search object for the view
    """

    def __init__(self, domain, case_types, criteria):
        self.domain = domain
        self.case_types = case_types
        self.criteria = criteria

        self.config = self._get_config()
        self.search_es = self._get_initial_search_es()

        self._assemble_optional_search_params()

    def _get_config(self):
        try:
            config = (CaseSearchConfig.objects
                      .prefetch_related('fuzzy_properties')
                      .prefetch_related('ignore_patterns')
                      .get(domain=self.domain))
        except CaseSearchConfig.DoesNotExist as e:
            from corehq.util.soft_assert import soft_assert
            _soft_assert = soft_assert(
                to="{}@{}.com".format('frener', 'dimagi'),
                notify_admins=False, send_to_ops=False
            )
            _soft_assert(
                False,
                "Someone in domain: {} tried accessing case search without a config".format(self.domain),
                e
            )
            config = CaseSearchConfig(domain=self.domain)
        return config

    def _get_initial_search_es(self):
        search_es = (CaseSearchES()
                     .domain(self.domain)
                     .case_type(self.case_types)
                     .is_closed(False)
                     .size(CASE_SEARCH_MAX_RESULTS)
                     .set_sorting_block(['_score', '_doc']))
        return search_es

    def _assemble_optional_search_params(self):
        self._add_xpath_query()
        self._add_owner_id()
        self._add_blacklisted_owner_ids()
        self._add_case_property_queries()

    def _validate_multiple_parameter_values(self, key, val):
        if not isinstance(val, list):
            return
        disallowed_multiple_value_parameters = [
            CASE_SEARCH_BLACKLISTED_OWNER_ID_KEY,
            'owner_id',
            CASE_SEARCH_XPATH_QUERY_KEY,
        ]
        is_daterange = any([v.startswith('__range__') for v in val])
        if key in disallowed_multiple_value_parameters or '/' in key or is_daterange:
            raise CaseFilterError(
                _("Multiple values are only supported for simple text and range searches"),
                key
            )

    def _add_xpath_query(self):
        query = self.criteria.pop(CASE_SEARCH_XPATH_QUERY_KEY, None)
        if query:
            self.search_es = self.search_es.xpath_query(self.domain, query)

    def _add_owner_id(self):
        owner_id = self.criteria.pop('owner_id', False)
        if owner_id:
            self.search_es = self.search_es.owner(owner_id)

    def _add_blacklisted_owner_ids(self):
        blacklisted_owner_ids = self.criteria.pop(CASE_SEARCH_BLACKLISTED_OWNER_ID_KEY, None)
        if blacklisted_owner_ids is not None:
            for blacklisted_owner_id in blacklisted_owner_ids.split(' '):
                self.search_es = self.search_es.blacklist_owner_id(blacklisted_owner_id)

    def _get_daterange_query(self, key, value):
        # Add query for specially formatted daterange param
        #   The format is __range__YYYY-MM-DD__YYYY-MM-DD, which is
        #   used by App manager case-search feature
        pattern = re.compile(r'__range__\d{4}-\d{2}-\d{2}__\d{4}-\d{2}-\d{2}')
        match = pattern.match(value)
        if match:
            _, _, startdate, enddate = value.split('__')
            return case_property_range_query(key, gte=startdate, lte=enddate),

    def _add_case_property_queries(self):
        for key, value in self.criteria.items():
            if key in UNSEARCHABLE_KEYS or key.startswith(SEARCH_QUERY_CUSTOM_VALUE):
                continue
            if isinstance(value, list) and '' in value:
                value = [v for v in value if v != '']
                if value:
                    value = value[0] if len(value) == 1 else value
                    query = filters.OR(
                        self._get_query(key, value),
                        case_property_missing(key),
                    )
                else:
                    query = case_property_missing(key)
            else:
                query = self._get_query(key, value)
            self.search_es = self.search_es.add_query(query, queries.MUST)

    def _get_query(self, key, value):
        self._validate_multiple_parameter_values(key, value)
        if not isinstance(value, list) and value.startswith('__range__'):
            return self._get_daterange_query(key, value)

        value = self._remove_ignored_patterns(key, value)
        fuzzy = key in self._fuzzy_properties
        if '/' in key:
            query = '{} = "{}"'.format(key, value)
            return build_filter_from_xpath(self.domain, query, fuzzy=fuzzy),
        else:
            return case_property_query(key, value, fuzzy=fuzzy)

    def _remove_ignored_patterns(self, case_property, value):
        for to_remove in self._patterns_to_remove[case_property]:
            if isinstance(value, list):
                value = [re.sub(to_remove, '', val) for val in value]
            else:
                value = re.sub(to_remove, '', value)
        return value

    @cached_property
    def _patterns_to_remove(self):
        patterns_by_property = defaultdict(list)
        for pattern in self.config.ignore_patterns.filter(domain=self.domain, case_type__in=self.case_types):
            patterns_by_property[pattern.case_property].append(re.escape(pattern.regex))
        return patterns_by_property

    @cached_property
    def _fuzzy_properties(self):
        return [
            prop for properties_config in
            self.config.fuzzy_properties.filter(domain=self.domain, case_type__in=self.case_types)
            for prop in properties_config.properties
        ]


def get_related_cases(domain, app_id, case_types, cases):
    """
    Fetch related cases that are necessary to display any related-case
    properties in the app requesting this case search.

    Returns list of CommCareCase objects for adding to CaseDBFixture.
    """
    if not cases:
        return []

    app = get_app_cached(domain, app_id)
    paths = [
        rel for rels in [get_related_case_relationships(app, case_type) for case_type in case_types]
        for rel in rels
    ]
    child_case_types = [
        _type for types in [get_child_case_types(app, case_type) for case_type in case_types]
        for _type in types
    ]

    results = []
    if paths:
        results.extend(get_related_case_results(domain, cases, paths))

    if child_case_types:
        results.extend(get_child_case_results(domain, cases, child_case_types))

    return results


def get_related_case_relationships(app, case_type):
    """
    Get unique case relationships used by search details in any modules that
    match the given case type and are configured for case search.

    Returns a set of relationships, e.g. {"parent", "host", "parent/parent"}
    """
    paths = set()
    for module in app.get_modules():
        if module.case_type == case_type and module_offers_search(module):
            for column in module.search_detail("short").columns + module.search_detail("long").columns:
                if not column.useXpathExpression:
                    parts = column.field.split("/")
                    if len(parts) > 1:
                        parts.pop()     # keep only the relationship: "parent", "parent/parent", etc.
                        paths.add("/".join(parts))
    return paths


def get_related_case_results(domain, cases, paths):
    """
    Given a set of cases and a set of case property paths,
    fetches ES documents for all cases referenced by those paths.
    """
    if not cases:
        return []

    results_cache = {}
    for path in paths:
        current_cases = cases
        parts = path.split("/")
        for index, identifier in enumerate(parts):
            fragment = "/".join(parts[:index + 1])
            if fragment in results_cache:
                current_cases = results_cache[fragment]
            else:
                indices = [case.get_index(identifier) for case in current_cases]
                related_case_ids = {i.referenced_id for i in indices if i}
                results = CaseSearchES().domain(domain).case_ids(related_case_ids).run().hits
                current_cases = [CommCareCase.wrap(flatten_result(result)) for result in results]
                results_cache[fragment] = current_cases

    results = []
    for path in paths:
        results.extend(results_cache[path])

    return results


def get_child_case_types(app, case_type):
    """
    Get child case types used by search detail tab nodesets in any modules
    that match the given case type and are configured for case search.

    Returns a set of case types
    """
    case_types = set()
    for module in app.get_modules():
        if module.case_type == case_type and module_offers_search(module):
            for tab in module.search_detail("long").tabs:
                if tab.has_nodeset and tab.nodeset_case_type:
                    case_types.add(tab.nodeset_case_type)

    return case_types


def get_child_case_results(domain, parent_cases, case_types):
    parent_case_ids = {c.case_id for c in parent_cases}
    query = CaseSearchES().domain(domain).case_type(case_types).get_child_cases(parent_case_ids, "parent")
    results = query.run().hits
    return [CommCareCase.wrap(flatten_result(result)) for result in results]
