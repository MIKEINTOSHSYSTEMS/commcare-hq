import csv
from gevent.pool import Pool

from django.core.management.base import BaseCommand
from django.core.management import call_command


DEVICE_ID = __name__ + ".run_all_management_command"


def run_command(command, *args, location=None, inactive_location=None):
    try:
        if inactive_location is not None:
            call_command(command, *args, location=location, inactive_location=inactive_location)
        elif location is not None:
            call_command(command, *args, location=location)
        else:
            call_command(command, *args)
    except Exception as e:
        return False, command, args, e
    return True, command, args, None


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('csv_file')
        parser.add_argument('--only-inactive', action='store_true', default=False)

    def handle(self, csv_file, **options):
        domains = []
        location_ids = {}
        with open(csv_file, newline='') as file:
            reader = csv.DictReader(file)
            for row in reader:
                domains.append(row['domain'])
                locations = {'active': {}, 'inactive': ''}
                if row['non_traveler_active_location_id'] != '':
                    locations['active']['non_traveler'] = (row['non_traveler_active_location_id'])
                if row['traveler_active_location_id'] != '':
                    locations['active']['traveler'] = (row['traveler_active_location_id'])
                locations['inactive'] = row['inactive_location_id']
                location_ids[row['domain']] = locations

        if len(set(domains)) != len(domains):
            domains = set(domains)
            print("Rows with duplicate domains were found from csv file. The commands for each domains will"
                  " run differently than the order of the csv file.")

        total_jobs = []
        jobs = []
        pool = Pool(20)
        if options["only_inactive"]:
            for domain in domains:
                jobs.append(pool.spawn(run_command, 'update_case_index_relationship', domain, 'contact',
                                       location=location_ids[domain]['active']['traveler'],
                                       inactive_location=location_ids[domain]['inactive']))
            pool.join()
            total_jobs.extend(jobs)
        else:
            for domain in domains:
                jobs.append(pool.spawn(run_command, 'update_case_index_relationship', domain, 'contact',
                                       location=location_ids[domain]['active']['traveler']))
                jobs.append(pool.spawn(run_command, 'add_hq_user_id_to_case', domain, 'checkin'))
                jobs.append(pool.spawn(run_command, 'update_owner_ids', domain, 'investigation'))
                jobs.append(pool.spawn(run_command, 'update_owner_ids', domain, 'checkin'))
            pool.join()
            total_jobs.extend(jobs)

            jobs = []
            second_pool = Pool(20)
            for domain in domains:
                for location in location_ids[domain]['active'].values():
                    jobs.append(second_pool.spawn(run_command, 'add_assignment_cases', domain, 'patient',
                                                  location=location))
                    jobs.append(second_pool.spawn(run_command, 'add_assignment_cases', domain, 'contact',
                                                  location=location))
            second_pool.join()
            total_jobs.extend(jobs)

        for job in total_jobs:
            success, command, args, exception = job.get()
            if success:
                print("SUCCESS: {} command for {}".format(command, args))
            else:
                print("COMMAND FAILED: {} while running {} for {})".format(exception, command, args))
