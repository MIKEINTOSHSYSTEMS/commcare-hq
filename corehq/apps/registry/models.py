from datetime import datetime

from autoslug import AutoSlugField
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField, ArrayField
from django.db import models
from django.utils.text import slugify

from corehq.apps.domain.utils import domain_name_stop_words
from corehq.apps.registry.exceptions import RegistryAccessDenied


def slugify_remove_stops(text):
    words = slugify(text).split('-')
    stop_words = domain_name_stop_words()
    return "-".join([word for word in words if word not in stop_words])


class RegistryManager(models.Manager):

    def owned_by_domain(self, domain, is_active=None):
        query = self.filter(domain=domain)
        if is_active is not None:
            query = query.filter(is_active=is_active)
        return query

    def accessible_to_domain(self, domain, slug=None, has_grants=False):
        query = (
            self.filter(is_active=True)
            .filter(
                invitations__domain=domain,
                invitations__accepted_on__isnull=False,
                invitations__rejected_on__isnull=True
            )
        )
        if slug:
            query = query.filter(slug=slug)
        if has_grants:
            query = query.filter(grants__to_domains__contains=[domain])
        return query


class DataRegistry(models.Model):
    domain = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    # slug used for referencing the registry in app suite files, APIs etc.
    slug = AutoSlugField(populate_from='name', unique_with='domain', slugify=slugify_remove_stops)
    is_active = models.BooleanField(default=True)
    schema = JSONField(null=True)

    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    objects = RegistryManager()

    def deactivate(self):
        self.is_active = False
        self.save()

    def check_access(self, domain):
        if not self.is_active:
            raise RegistryAccessDenied()
        invites = self.invitations.filter(domain=domain)
        if not invites:
            raise RegistryAccessDenied()
        invite = invites[0]
        if not invite.accepted_on or invite.rejected_on:
            raise RegistryAccessDenied()
        return True


class RegistryInvitation(models.Model):
    registry = models.ForeignKey("DataRegistry", related_name="invitations", on_delete=models.CASCADE)
    domain = models.CharField(max_length=255)
    created_on = models.DateTimeField(auto_now_add=True)
    accepted_on = models.DateTimeField(null=True)
    accepted_by = models.ForeignKey(
        User, related_name="registry_accepted_invitations", on_delete=models.CASCADE, null=True
    )
    rejected_on = models.DateTimeField(null=True)
    rejected_by = models.ForeignKey(
        User, related_name="registry_rejected_invitations", on_delete=models.CASCADE, null=True
    )

    class Meta:
        unique_together = ("registry", "domain")

    def accept(self, accepted_by):
        self.accepted_on = datetime.utcnow()
        self.accepted_by = accepted_by
        self.save()

    def reject(self, rejected_by):
        self.rejected_on = datetime.utcnow()
        self.rejected_by = rejected_by
        self.save()


class RegistryGrant(models.Model):
    registry = models.ForeignKey("DataRegistry", related_name="grants", on_delete=models.CASCADE)
    from_domain = models.CharField(max_length=255)
    to_domains = ArrayField(models.CharField(max_length=255))


class RegistryPermission(models.Model):
    registry = models.ForeignKey("DataRegistry", related_name="permissions", on_delete=models.CASCADE)
    domain = models.CharField(max_length=255)
    read_only_group_id = models.CharField(max_length=255, null=True)

    class Meta:
        unique_together = ('registry', 'domain')
