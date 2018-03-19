from __future__ import absolute_import
from __future__ import unicode_literals
from corehq.motech.openmrs.logger import logger
from corehq.motech.openmrs.repeater_helpers import (
    CaseTriggerInfo,
    OpenmrsResponse,
    create_visit,
    get_patient,
    update_person_properties,
    update_person_name,
    update_person_address,
    create_person_address,
    update_person_attribute,
    create_person_attribute,
)
from dimagi.utils.parsing import string_to_utc_datetime


def send_openmrs_data(requests, form_json, openmrs_config, case_trigger_infos, form_question_values):
    """
    Updates an OpenMRS patient and creates visits

    :return: A response-like object that can be used by Repeater.handle_response
    """
    response = None
    logger.debug('Fetching OpenMRS patient UUIDs with ', case_trigger_infos)
    for info in case_trigger_infos:
        assert isinstance(info, CaseTriggerInfo)
        response = sync_openmrs_patient(requests, info, form_json, form_question_values, openmrs_config)
    return response or OpenmrsResponse(404, 'Not Found')


def sync_person_attributes(requests, info, openmrs_config, person_uuid, attributes):
    existing_person_attributes = {
        attribute['attributeType']['uuid']: (attribute['uuid'], attribute['value'])
        for attribute in attributes
    }
    for person_attribute_type, value_source in openmrs_config.case_config.person_attributes.items():
        value = value_source.get_value(info)
        if person_attribute_type in existing_person_attributes:
            attribute_uuid, existing_value = existing_person_attributes[person_attribute_type]
            if value != existing_value:
                update_person_attribute(requests, person_uuid, attribute_uuid, person_attribute_type, value)
        else:
            create_person_attribute(requests, person_uuid, person_attribute_type, value)


def create_visits(requests, info, form_json, form_question_values, openmrs_config, person_uuid):
    provider_uuid = getattr(openmrs_config, 'openmrs_provider', None)
    info.form_question_values.update(form_question_values)
    for form_config in openmrs_config.form_configs:
        logger.debug('Send visit for form?', form_config, form_json)
        if form_config.xmlns == form_json['form']['@xmlns']:
            logger.debug('Yes')
            create_visit(
                requests,
                person_uuid=person_uuid,
                provider_uuid=provider_uuid,
                visit_datetime=string_to_utc_datetime(form_json['form']['meta']['timeEnd']),
                values_for_concept={obs.concept: [obs.value.get_value(info)]
                                    for obs in form_config.openmrs_observations
                                    if obs.value.get_value(info)},
                encounter_type=form_config.openmrs_encounter_type,
                openmrs_form=form_config.openmrs_form,
                visit_type=form_config.openmrs_visit_type,
                # location_uuid=,  # location of case owner (CHW) > location[meta][openmrs_uuid]
            )


def sync_openmrs_patient(requests, info, form_json, form_question_values, openmrs_config):
    patient = get_patient(requests, info, openmrs_config)
    if patient is None:
        raise ValueError('CommCare patient was not found in OpenMRS')
    person_uuid = patient['person']['uuid']
    logger.debug('OpenMRS patient found: ', person_uuid)
    update_person_properties(requests, info, openmrs_config, person_uuid)

    name_uuid = patient['person']['preferredName']['uuid']
    update_person_name(requests, info, openmrs_config, person_uuid, name_uuid)

    address_uuid = patient['person']['preferredAddress']['uuid'] if patient['person']['preferredAddress'] else None
    if address_uuid:
        update_person_address(requests, info, openmrs_config, person_uuid, address_uuid)
    else:
        create_person_address(requests, info, openmrs_config, person_uuid)

    sync_person_attributes(requests, info, openmrs_config, person_uuid, patient['person']['attributes'])

    create_visits(requests, info, form_json, form_question_values, openmrs_config, person_uuid)

    return OpenmrsResponse(200, 'OK')
