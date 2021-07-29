from django.core.management.base import BaseCommand

from corehq.apps.users.models_sql import SQLPermission, SQLUserRole


class Command(BaseCommand):
    help = "Adds download_reports permission to user role if not already present."

    def handle(self, **options):
        permission, created = SQLPermission.objects.get_or_create(value='download_reports')
        for role in SQLUserRole.objects.exclude(rolepermission__permission_fk_id=permission.id).iterator():
            rp, created = role.rolepermission_set.get_or_create(permission_fk=permission,
                                                                defaults={"allow_all": True})
            if created:
                role._migration_do_sync()
