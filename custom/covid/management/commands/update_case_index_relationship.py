from xml.etree import cElementTree as ElementTree

from custom.covid.management.commands.update_cases import CaseUpdateCommand

from casexml.apps.case.mock import CaseBlock
from dimagi.utils.chunked import chunked

from corehq.apps.hqcase.utils import submit_case_blocks
from corehq.form_processor.interfaces.dbaccessors import CaseAccessors

'''This command has an optional argument '--location' that will exclude all cases with that location. If the
case_type is lab_result, the owner_id of that extension case is set to '-'. '''

BATCH_SIZE = 100
DEVICE_ID = __name__ + ".update_case_index_relationship"


def should_skip(case, traveler_location_id):
    if traveler_location_id is None:
        return len(case.indices) != 1
    return len(case.indices) != 1 or case.get_case_property('owner_id') == traveler_location_id


def needs_update(case):
    index = case.indices[0]
    return index.referenced_type == "patient" and index.relationship == "child"


def get_owner_id(case_type):
    if case_type == 'lab_result':
        return '-'
    return None


class Command(CaseUpdateCommand):
    help = ("Updates all case indices of a specfied case type to use an extension relationship instead of parent.")

    def case_block(self, case, owner_id):
        index = case.indices[0]
        return ElementTree.tostring(CaseBlock.deprecated_init(
            create=False,
            case_id=case.case_id,
            owner_id=owner_id,
            index={index.identifier: (index.referenced_type, index.referenced_id, "extension")},
        ).as_xml(), encoding='utf-8').decode('utf-8')

    def update_cases(self, domain, case_type, user_id):
        accessor = CaseAccessors(domain)
        case_ids = accessor.get_case_ids_in_domain(case_type)
        print(f"Found {len(case_ids)} {case_type} cases in {domain}")
        traveler_location_id = self.location

        case_blocks = []
        skip_count = 0
        for case in accessor.iter_cases(case_ids):
            if should_skip(case, traveler_location_id):
                skip_count += 1
            elif needs_update(case):
                owner_id = get_owner_id(case_type)
                case_blocks.append(self.case_block(case, owner_id))
        print(f"{len(case_blocks)} to update in {domain}, {skip_count} cases have skipped due to"
              f" multiple indices.")

        total = 0
        for chunk in chunked(case_blocks, BATCH_SIZE):
            submit_case_blocks(chunk, domain, device_id=DEVICE_ID, user_id=user_id)
            total += len(chunk)
            print("Updated {} cases on domain {}".format(total, domain))

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--location', type=str, default=None)
