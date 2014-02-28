from corehq.apps.accounting.tests.base_tests import BaseAccountingTest
from toggle.models import Toggle
from corehq import toggles
from corehq.apps.accounting import generator
from corehq.apps.accounting.models import (
    Subscription, BillingAccount, DefaultProductPlan, SoftwarePlanEdition,
)
from corehq.apps.users.models import (
    Permissions, UserRole, UserRolePresets, WebUser, CommCareUser,
)


class TestUserRoleSubscriptionChanges(BaseAccountingTest):
    min_subscription_length = 3

    def setUp(self):
        self.domain = generator.arbitrary_domain()
        UserRole.init_domain_with_presets(self.domain.name)
        self.user_roles = UserRole.by_domain(self.domain.name)
        self.custom_role = UserRole.get_or_create_with_permissions(
            self.domain.name,
            Permissions(edit_apps=True, edit_web_users=True),
            "Custom Role"
        )
        self.custom_role.save()
        self.read_only_role = UserRole.get_read_only_role_by_domain(self.domain.name)

        self.admin_user = generator.arbitrary_web_user()
        self.admin_user.add_domain_membership(self.domain.name, is_admin=True)
        self.admin_user.save()

        self.web_users = []
        self.commcare_users = []
        for role in [self.custom_role] + self.user_roles:
            web_user = generator.arbitrary_web_user()
            web_user.add_domain_membership(self.domain.name, role_id=role.get_id)
            web_user.save()
            self.web_users.append(web_user)

            commcare_user = generator.arbitrary_commcare_user(
                domain=self.domain.name)
            commcare_user.set_role(self.domain.name, role.get_qualified_id())
            commcare_user.save()
            self.commcare_users.append(commcare_user)

        # toggle until release
        self.toggle = Toggle(
            slug=toggles.ACCOUNTING_PREVIEW.slug,
            enabled_users=[self.admin_user.username],
        )
        self.toggle.save()

        self.account = BillingAccount.get_or_create_account_by_domain(
            self.domain.name,created_by=self.admin_user.username)[0]
        self.advanced_plan = DefaultProductPlan.get_default_plan_by_domain(
            self.domain.name,edition=SoftwarePlanEdition.ADVANCED)

    def test_cancellation(self):
        subscription = Subscription.new_domain_subscription(
            self.account, self.domain.name, self.advanced_plan,
            web_user=self.admin_user.username
        )
        self._change_std_roles()
        subscription.cancel_subscription(web_user=self.admin_user.username)

        custom_role = UserRole.get(self.custom_role.get_id)
        custom_web_user = WebUser.get(self.web_users[0].get_id)
        custom_commcare_user = CommCareUser.get(self.commcare_users[0].get_id)

        self.assertTrue(custom_role.is_archived)
        self.assertEqual(
            custom_web_user.get_domain_membership(self.domain.name).role_id,
            self.read_only_role.get_id
        )
        self.assertIsNone(
            custom_commcare_user.get_domain_membership(self.domain.name).role_id
        )
        self.assertInitialRoles()
        self.assertStdUsers()

    def test_resubscription(self):
        subscription = Subscription.new_domain_subscription(
            self.account, self.domain.name, self.advanced_plan,
            web_user=self.admin_user.username
        )
        self._change_std_roles()
        subscription.cancel_subscription(web_user=self.admin_user.username)
        custom_role = UserRole.get(self.custom_role.get_id)
        self.assertTrue(custom_role.is_archived)
        subscription = Subscription.new_domain_subscription(
            self.account, self.domain.name, self.advanced_plan,
            web_user=self.admin_user.username
        )
        custom_role = UserRole.get(self.custom_role.get_id)
        self.assertFalse(custom_role.is_archived)

        custom_web_user = WebUser.get(self.web_users[0].get_id)
        custom_commcare_user = CommCareUser.get(self.commcare_users[0].get_id)
        self.assertEqual(
            custom_web_user.get_domain_membership(self.domain.name).role_id,
            self.read_only_role.get_id
        )
        self.assertIsNone(
            custom_commcare_user.get_domain_membership(self.domain.name).role_id
        )

        self.assertInitialRoles()
        self.assertStdUsers()
        subscription.cancel_subscription(web_user=self.admin_user.username)

    def _change_std_roles(self):
        for u in self.user_roles:
            user_role = UserRole.get(u.get_id)
            user_role.permissions = Permissions(
                view_reports=True, edit_commcare_users=True, edit_apps=True,
                edit_data=True
            )
            user_role.save()

    def assertInitialRoles(self):
        for u in self.user_roles:
            user_role = UserRole.get(u.get_id)
            self.assertEqual(
                user_role.permissions,
                UserRolePresets.get_permissions(user_role.name)
            )

    def assertStdUsers(self):
        for ind, wu in enumerate(self.web_users[1:]):
            web_user = WebUser.get(wu.get_id)
            self.assertEqual(
                web_user.get_domain_membership(self.domain.name).role_id,
                self.user_roles[ind].get_id
            )

        for ind, cc in enumerate(self.commcare_users[1:]):
            commcare_user = CommCareUser.get(cc.get_id)
            self.assertEqual(
                commcare_user.get_domain_membership(self.domain.name).role_id,
                self.user_roles[ind].get_id
            )

    def tearDown(self):
        self.domain.delete()
        self.admin_user.delete()
        self.toggle.delete()
        generator.delete_all_subscriptions()
        generator.delete_all_accounts()
        super(TestUserRoleSubscriptionChanges, self).tearDown()
