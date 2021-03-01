from collections import namedtuple
from typing import Iterable, List, Optional, Type

import attr

from corehq.motech.finders import le_days_diff, le_levenshtein_percent
from jsonpath_ng.ext.parser import parse as jsonpath_parse

from corehq.motech.utils import simplify_list

CandidateScore = namedtuple('CandidateScore', 'candidate score')


class DuplicateWarning(Warning):
    pass


class ResourceMatcher:
    """
    Finds matching FHIR resources.

    The properties of resources are compared. Each matching property has
    a weight. The sum of the weights give a score. If the score is
    greater than 1, the resources are considered a match.

    If more than one candidate matches, but one has a significantly
    higher score than the rest, it is the match. Otherwise a
    ``DuplicateWarning`` exception is raised.
    """

    property_weights: List['PropertyWeight']
    confidence_margin = 0.5

    def __init__(self, resource: dict):
        self.resource = resource

    def find_match(self, candidates: Iterable[dict]):
        matches = self.find_matches(candidates, keep_dups=False)
        match = simplify_list(matches)
        if isinstance(match, list):
            raise DuplicateWarning('Duplicate matches found for resource '
                                   f'{self.resource}')
        return match

    def find_matches(self, candidates: Iterable[dict], *, keep_dups=True):
        """
        Returns a list of matches.

        If ``keep_dups`` is False, allows for an arbitrary number of
        candidates but only returns the best two, or fewer.
        """

        def top_two(list_):
            return sorted(list_, key=lambda l: l.score, reverse=True)[:2]

        candidates_scores = []
        for candidate in candidates:
            score = self.get_score(candidate)
            if score >= 1:
                candidates_scores.append(CandidateScore(candidate, score))
            if not keep_dups:
                candidates_scores = top_two(candidates_scores)

        if len(candidates_scores) > 1:
            best, second = top_two(candidates_scores)
            if best.score / second.score >= 1 + self.confidence_margin:
                return [best.candidate]
        return [cs.candidate for cs in candidates_scores]

    def get_score(self, candidate):
        return sum(self.iter_weights(candidate))

    def iter_weights(self, candidate):
        for pw in self.property_weights:
            is_match = pw.method.is_match(self.resource, candidate)
            if is_match is None:
                # method was unable to compare values
                continue
            yield pw.weight if is_match else pw.negative_weight


class ComparisonMethod:
    """
    A method of comparing resource properties.
    """

    def __init__(self, jsonpath: str):
        self.jsonpath = jsonpath_parse(jsonpath)

    def is_match(self, resource: dict, candidate: dict) -> Optional[bool]:
        a = simplify_list([x.value for x in self.jsonpath.find(resource)])
        b = simplify_list([x.value for x in self.jsonpath.find(candidate)])
        if a is None or b is None:
            return None
        return self.compare(a, b)

    @staticmethod
    def compare(a, b) -> bool:
        raise NotImplementedError


class IsEqual(ComparisonMethod):

    @staticmethod
    def compare(a, b):
        return a == b


class GivenName(ComparisonMethod):

    @staticmethod
    def compare(a, b):
        return any(a_name == b_name for a_name, b_name in zip(a, b))


class Age(ComparisonMethod):

    @staticmethod
    def compare(a, b):
        max_days = 364
        return le_days_diff(max_days, a, b)


class OrganizationName(ComparisonMethod):

    @staticmethod
    def compare(a, b):
        percent = 0.2
        return le_levenshtein_percent(percent, a.lower(), b.lower())


@attr.s(auto_attribs=True)
class PropertyWeight:
    """
    Associates a matching property with a weight
    """
    jsonpath: str
    weight: float
    method_class: Type[ComparisonMethod] = IsEqual
    negative_weight: float = 0  # Score negatively if values are different

    @property
    def method(self):
        return self.method_class(self.jsonpath)


class PersonMatcher(ResourceMatcher):
    """
    Finds matching FHIR Persons
    """
    property_weights = [
        PropertyWeight('$.name[0].given', 0.3, GivenName),
        # PropertyWeight('$.name[0].given', 0.1, AnyGivenName),
        PropertyWeight('$.name[0].family', 0.4),
        PropertyWeight('$.telecom[0].value', 0.4),
        PropertyWeight('$.gender', 0.05, negative_weight=0.6),
        PropertyWeight('$.birthDate', 0.1),
        PropertyWeight('$.birthDate', 0.05, Age, negative_weight=0.2),
    ]


class PatientMatcher(ResourceMatcher):
    """
    Finds matching FHIR Patients
    """
    property_weights = PersonMatcher.property_weights + [
        PropertyWeight('$.multipleBirthInteger', 0.1)
    ]


class OrganizationMatcher(ResourceMatcher):
    property_weights = [
        PropertyWeight('$.name', 0.8, OrganizationName),
        PropertyWeight('$.telecom[0].value', 0.4),
    ]


def get_matcher(resource: dict) -> ResourceMatcher:
    """
    Returns a subclass of ``ResourceMatcher`` instantiated with
    ``resource``.

    .. IMPORTANT::
       ``get_matcher()`` assumes that subclasses of ``ResourceMatcher``
       are named for the resource type they are implemented for.
       e.g. ``PatientMatcher`` matches Patient resources.

    """
    suffix = len('Matcher')
    classes_by_resource_type = {cls.__name__[:-suffix]: cls
                                for cls in ResourceMatcher.__subclasses__()}
    try:
        matcher_class = classes_by_resource_type[resource['resourceType']]
    except KeyError:
        raise NotImplementedError(
            'ResourceMatcher not implemented for resource type '
            f"{resource['resourceType']!r}"
        )
    return matcher_class(resource)
