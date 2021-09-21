/**
 * This file controls the UI for the enterprise users page.
 * This page is based on the main "Current Users" panel on
 * the web users page, but it displays a different set of columns
 * and adds in rows for mobile workers linked to the web users.
 */
hqDefine("users/js/enterprise_users", [
    "jquery",
    "knockout",
    "underscore",
    "hqwebapp/js/initial_page_data",
    "users/js/web_users_list",
    "hqwebapp/js/components.ko",    // pagination and search box widgets
], function (
    $,
    ko,
    _,
    initialPageData,
    webUsersList
) {
    var UserModel = function (options) {
        var self = _.defaults(options, {
            profile: null,
            loginAsUser: null,
            loginAsUserCount: 0,
            inactiveMobileCount: 0,
        });

        // Only varies for mobile users
        self.visible = ko.observable(!self.loginAsUser);

        // Only relevant for web users
        self.expanded = ko.observable(false);


        return self;
    };

    var enterpriseUsersList = function (options) {

        var self = webUsersList(options);

        self.toggleLoginAsUsers = function (webUser) {
            webUser.expanded(!webUser.expanded());
            _.each(self.users(), function (user) {
                if (user.loginAsUser === webUser.username) {
                    user.visible(webUser.expanded() && user.is_active !== self.showDeactivated());
                }
            });
        };

        self.showDeactivated = ko.observable(false);

        self.toggleDeactivatedText = ko.computed(function () {
            return self.showDeactivated() ? gettext("Hide Deactivated Mobile Workers") : gettext("Show Deactivated Mobile Workers");
        });

        self.toggleDeactivated = function () {
            _.each(self.users(), function (user) {
                if (!user.loginAsUser) {
                    user.expanded(false);
                    if (self.showDeactivated()) {
                        user.visible(user.inactiveMobileCount > 0);
                    } else {
                        user.visible(true);
                    }
                } else {
                    user.visible(false);
                }
            });
        };

        self.showDeactivated.subscribe(function () {
            self.toggleDeactivated();
        });

        return self;
    };

    $(function () {
        $("#web-users-panel").koApplyBindings(enterpriseUsersList({
            url: initialPageData.reverse("paginate_enterprise_users"),
            userModel: UserModel,
        }));
    });
});
