var url = hqImport('hqwebapp/js/urllib.js').reverse;

function SystemUsageController($http, $log, $routeParams) {
    var vm = this;
    vm.data = {};
    vm.label = "Program Summary";
    vm.tooltipPlacement = "right";
    vm.filters = ['month', 'age'];
    vm.step = $routeParams.step;

    vm.getDataForStep = function(step) {
        var get_url = url('program_summary', step);
        $http({
            method: "GET",
            url: get_url,
            params: {},
        }).then(
            function (response) {
                vm.data = response.data.records;
            },
            function (error) {
                $log.error(error);
            }
        );
    };

    vm.steps = {
        "system_usage": {"route": "/system_usage", "label": "System Usage", "data": null},
        "maternal_child": {"route": "/maternal_child", "label": "Maternal & Child Health", "data": null},
        "icds_cas_reach": {"route": "/icds_cas_reach", "label": "ICDS-CAS Reach", "data": null},
        "demographics": {"route": "/demographics", "label": "Demographics", "data": null},
        "awc_infrastructure": {"route": "/awc_infrastructure", "label": "AWC Infrastructure", "data": null},
    };

    vm.getDataForStep(vm.step);
}

SystemUsageController.$inject = ['$http', '$log', '$routeParams'];

window.angular.module('icdsApp').directive('systemUsage', function() {
    return {
        restrict: 'E',
        templateUrl: url('icds-ng-template', 'system-usage.directive'),
        bindToController: true,
        controller: SystemUsageController,
        controllerAs: '$ctrl',
    };
});
