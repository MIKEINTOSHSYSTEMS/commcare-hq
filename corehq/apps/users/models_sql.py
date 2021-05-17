from django.contrib.postgres.fields import ArrayField
from django.db import models

import settings
from corehq.apps.users.landing_pages import ALL_LANDING_PAGES
from corehq.util.models import ForeignValue, foreign_value_init
from corehq.util.quickcache import quickcache
from dimagi.utils.couch.migration import SyncSQLToCouchMixin


class StaticRole:
    @classmethod
    def domain_admin(cls, domain):
        from corehq.apps.users.models import Permissions
        return StaticRole(domain, "Admin", Permissions.max())

    @classmethod
    def domain_default(cls, domain):
        from corehq.apps.users.models import Permissions
        return StaticRole(domain, None, Permissions())

    def __init__(self, domain, name, permissions):
        self.domain = domain
        self.name = name
        self.default_landing_page = None
        self.is_non_admin_editable = False
        self.is_archived = False
        self.upstream_id = None
        self.couch_id = None
        self.permissions = permissions
        self.assignable_by = []

    def get_qualified_id(self):
        return self.name.lower() if self.name else None

    @property
    def get_id(self):
        return None

    @property
    def cache_version(self):
        return self.name

    def to_json(self):
        return role_to_dict(self)


class UserRoleManager(models.Manager):

    def by_couch_id(self, couch_id):
        return SQLUserRole.objects.get(couch_id=couch_id)


class SQLUserRole(SyncSQLToCouchMixin, models.Model):
    domain = models.CharField(max_length=128, null=True)
    name = models.CharField(max_length=128, null=True)
    default_landing_page = models.CharField(
        max_length=64, choices=[(page.id, page.name) for page in ALL_LANDING_PAGES], null=True
    )
    # role can be assigned by all non-admins
    is_non_admin_editable = models.BooleanField(null=False, default=False)
    is_archived = models.BooleanField(null=False, default=False)
    upstream_id = models.IntegerField(null=True)
    couch_id = models.CharField(max_length=126, null=True)

    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    objects = UserRoleManager()

    class Meta:
        db_table = "users_userrole"
        indexes = (
            models.Index(fields=("domain",)),
            models.Index(fields=("couch_id",)),
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._cached_permissions.clear(self)
        self._cached_assignable_by.clear(self)

    @classmethod
    def by_domain(cls, domain, include_archived=False):
        query = SQLUserRole.objects.filter(domain=domain)
        if not include_archived:
            query.filter(is_archived=False)
        return list(query.prefetch_related('rolepermission_set'))

    @classmethod
    def _migration_get_fields(cls):
        return [
            "domain",
            "name",
            "default_landing_page",
            "is_non_admin_editable",
            "is_archived",
        ]

    @classmethod
    def _migration_get_couch_model_class(cls):
        from corehq.apps.users.models import UserRole
        return UserRole

    def _migration_sync_submodels_to_couch(self, couch_object):
        if self.upstream_id:
            upstream_role = SQLUserRole.objects.get(id=self.upstream_id)
            couch_object.upstream_id = upstream_role.couch_id
        else:
            couch_object.upstream_id = None
        couch_object.permissions = self.permissions
        couch_object.assignable_by = list(
            self.roleassignableby_set.values_list('assignable_by_role__couch_id', flat=True)
        )

    def to_json(self):
        return role_to_dict(self)

    @property
    def get_id(self):
        assert self.couch_id is not None
        return self.couch_id

    def get_qualified_id(self):
        return 'user-role:%s' % self.get_id

    def set_permissions(self, permission_infos):
        permissions_by_name = {
            rp.permission: rp
            for rp in self.rolepermission_set.all()
        }
        for info in permission_infos:
            perm = permissions_by_name.pop(info.name, None)
            if not perm:
                new_perm = RolePermission.from_permission_info(self, info)
                new_perm.save()
            elif (perm.allow_all, perm.allowed_items) != (info.allow_all, info.allowed_items):
                perm.allow_all = info.allow_all
                perm.allowed_items = info.allowed_items
                perm.save()

        if permissions_by_name:
            old_ids = [old.id for old in permissions_by_name.values()]
            RolePermission.objects.filter(id__in=old_ids).delete()
        self._cached_permissions.clear(self)

    def get_permission_infos(self):
        return [rp.as_permission_info() for rp in self.rolepermission_set.all()]

    @property
    def permissions(self):
        return self._cached_permissions()

    @quickcache(["self.id"], skip_arg=lambda _: settings.UNIT_TESTING)
    def _cached_permissions(self):
        from corehq.apps.users.models import Permissions
        return Permissions.from_permission_list(self.get_permission_infos())

    def set_assignable_by(self, role_ids):
        if not role_ids:
            self.roleassignableby_set.all().delete()
            return

        assignments_by_role_id = {
            assignment[0]: assignment[1]
            for assignment in self.roleassignableby_set.values_list('assignable_by_role_id', 'id').all()
        }

        for role_id in role_ids:
            assignment = assignments_by_role_id.pop(role_id, None)
            if not assignment:
                assignment = RoleAssignableBy(role=self, assignable_by_role_id=role_id)
                assignment.save()

        if assignments_by_role_id:
            old_ids = list(assignments_by_role_id.values())
            RoleAssignableBy.objects.filter(id__in=old_ids).delete()
        self._cached_assignable_by.clear(self)

    def get_assignable_by(self):
        return list(self.roleassignableby_set.select_related("assignable_by_role").all())

    @property
    def assignable_by(self):
        return self._cached_assignable_by()

    @quickcache(["self.id"], skip_arg=lambda _: settings.UNIT_TESTING)
    def _cached_assignable_by(self):
        return list(
            self.roleassignableby_set.values_list('assignable_by_role_id', flat=True)
        )

    @property
    def cache_version(self):
        return self.modified_on.isoformat()


@foreign_value_init
class RolePermission(models.Model):
    role = models.ForeignKey("SQLUserRole", on_delete=models.CASCADE)
    permission_fk = models.ForeignKey("SQLPermission", on_delete=models.CASCADE)
    permission = ForeignValue(permission_fk)

    # if True allow access to all items
    # if False only allow access to listed items
    allow_all = models.BooleanField(default=True)

    # current max len in 119 chars
    allowed_items = ArrayField(models.CharField(max_length=256), blank=True, null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="users_rolepermission_valid_allow",
                check=~models.Q(allow_all=True, allowed_items__len__gt=0)
            )
        ]

    @staticmethod
    def from_permission_info(role, info):
        return RolePermission(
            role=role, permission=info.name, allow_all=info.allow_all, allowed_items=info.allowed_items
        )

    def as_permission_info(self):
        from corehq.apps.users.models import PermissionInfo
        allow = PermissionInfo.ALLOW_ALL if self.allow_all else tuple(self.allowed_items)
        return PermissionInfo(self.permission, allow=allow)


class SQLPermission(models.Model):
    value = models.CharField(max_length=255, unique=True)

    class Meta:
        db_table = "users_permission"

    @classmethod
    def create_all(cls):
        from corehq.apps.users.models import Permissions
        for name in Permissions.permission_names():
            SQLPermission.objects.get_or_create(value=name)


class RoleAssignableBy(models.Model):
    role = models.ForeignKey("SQLUserRole", on_delete=models.CASCADE)
    assignable_by_role = models.ForeignKey(
        "SQLUserRole", on_delete=models.CASCADE, related_name="can_assign_roles"
    )


def migrate_role_permissions_to_sql(user_role, sql_role):
    sql_role.set_permissions(user_role.permissions.to_list())


def migrate_role_assignable_by_to_sql(couch_role, sql_role):
    from corehq.apps.users.models import UserRole

    assignable_by_mapping = {
        ids[0]: ids[1] for ids in
        SQLUserRole.objects.filter(couch_id__in=couch_role.assignable_by).values_list('couch_id', 'id')
    }
    if len(assignable_by_mapping) != len(couch_role.assignable_by):
        for couch_id in couch_role.assignable_by:
            if couch_id not in assignable_by_mapping:
                assignable_by_sql_role = UserRole.get(couch_id)._migration_do_sync()  # noqa
                assert assignable_by_sql_role is not None
                assignable_by_mapping[couch_id] = assignable_by_sql_role.id

    sql_role.set_assignable_by(list(assignable_by_mapping.values()))


def role_to_dict(role):
    data = {}
    for field in SQLUserRole._migration_get_fields():
        data[field] = getattr(role, field)
    data["upstream_id"] = role.upstream_id
    data["permissions"] = role.permissions.to_json()
    data["assignable_by"] = role.assignable_by
    if role.couch_id:
        data["_id"] = role.id
    return data
