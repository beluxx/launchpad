/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Control enabling/disabling form elements on the +new-recipe page.
 *
 * @module Y.lp.code.util
 * @requires node
 */
YUI.add('lp.code.util', function(Y) {
var ns = Y.namespace('lp.code.util');

var update_branch_unique_name = function() {
    var unique_name = Y.one("#branch-unique-name");
    var owner = Y.one("[id='field.owner']").get('value');
    var name = Y.one("[id='field.name']").get('value');
    if (name == '') {
        name = '<name>';
    }
    var branch_name = "~" + owner + "/" + target_name + "/" + name;
    unique_name.set('text', branch_name);
};

var hookUpBranchFieldFunctions = function () {
    var owner = Y.one("[id='field.owner']");
    owner.on('keyup', update_branch_unique_name);
    owner.on('change', update_branch_unique_name);
    var name = Y.one("[id='field.name']");
    name.on('keyup', update_branch_unique_name);
    name.on('change', update_branch_unique_name);
    Y.one('#branch-unique-name-div').setStyle('display', 'block');
    update_branch_unique_name();
};

var hookUpBranchFilterSubmission = function() {
    var submit_filter = function (e) {
        Y.DOM.byId('filter_form').submit();
    };

    Y.one("[id='field.lifecycle']").on('change', submit_filter);
    var sortby = Y.one("[id='field.sort_by']");
    if (Y.Lang.isValue(sortby)) {
        sortby.on('change', submit_filter)
    }
};

var hookUpDailyBuildsFilterSubmission = function() {
    var submit_filter = function (e) {
        Y.DOM.byId('filter_form').submit();
    };

    Y.one("[id='field.when_completed_filter']").on(
        'change', submit_filter);
};

ns.hookUpBranchFieldFunctions = hookUpBranchFieldFunctions;
ns.hookUpBranchFilterSubmission = hookUpBranchFilterSubmission;
ns.hookUpDailyBuildsFilterSubmission = hookUpDailyBuildsFilterSubmission;

}, "0.1", {"requires": ["node", "dom"]});

