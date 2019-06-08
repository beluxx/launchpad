/* Copyright 2015-2016 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Test driver for snap.edit.js.
 */
YUI.add('lp.snappy.snap.edit.test', function(Y) {
    var tests = Y.namespace('lp.snappy.snap.edit.test');
    var module = Y.lp.snappy.snap.edit;
    tests.suite = new Y.Test.Suite('snappy.snap.edit Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'snappy.snap.edit_tests',

        setUp: function() {
            this.tbody = Y.one('#snap.edit');

            // Get the widgets with event handlers attached.
            this.vcs_bzr = Y.DOM.byId('field.vcs.Bazaar');
            this.vcs_git = Y.DOM.byId('field.vcs.Git');
            this.auto_build = Y.DOM.byId('field.auto_build');

            // Get the input widgets.
            this.input_branch = Y.DOM.byId('field.branch');
            this.input_git_repository = Y.DOM.byId('field.git_ref.repository');
            this.input_git_path = Y.DOM.byId('field.git_ref.path');
        },

        tearDown: function() {
            delete this.tbody;
        },

        test_handlers_connected: function() {
            // Manually invoke the setup function to ensure the handlers are
            // set.
            module.setup();

            var check_handler = function(field, expected) {
                var custom_events = Y.Event.getListeners(field, 'click');
                var click_event = custom_events[0];
                var subscribers = click_event.subscribers;
                Y.each(subscribers, function(sub) {
                    Y.Assert.isTrue(sub.contains(expected),
                                    'handler not set up');
                });
            };

            check_handler(this.vcs_bzr, module.onclick_vcs);
            check_handler(this.vcs_git, module.onclick_vcs);
            check_handler(this.auto_build, module.onclick_auto_build);
        },

        test_select_vcs_bzr: function() {
            this.vcs_bzr.checked = true;
            module.onclick_vcs();
            // The branch input field is enabled.
            Y.Assert.isFalse(this.input_branch.disabled,
                             'branch field disabled');
            // The git_ref.repository and git_ref.path input fields are
            // disabled.
            Y.Assert.isTrue(this.input_git_repository.disabled,
                            'git_ref.repository field not disabled');
            Y.Assert.isTrue(this.input_git_path.disabled,
                            'git_ref.path field not disabled');
        },

        test_select_vcs_git: function() {
            this.vcs_git.checked = true;
            module.onclick_vcs();
            // The branch input field is disabled.
            Y.Assert.isTrue(this.input_branch.disabled,
                            'branch field not disabled');
            // The git_ref.repository and git_ref.path input fields are
            // enabled.
            Y.Assert.isFalse(this.input_git_repository.disabled,
                             'git_ref.repository field disabled');
            Y.Assert.isFalse(this.input_git_path.disabled,
                             'git_ref.path field disabled');
        },

        test_check_auto_build: function() {
            var fields = [
                'auto_build_archive.option.primary',
                'auto_build_archive.option.ppa',
                'auto_build_archive.ppa',
                'auto_build_pocket'
                ];
            var field;
            var i;
            module.setup();
            for (i = 0; i < fields.length; i++) {
                field = Y.DOM.byId('field.' + fields[i]);
                Y.Assert.isTrue(
                    field.disabled, fields[i] + ' field not disabled');
            }
            this.auto_build.checked = true;
            module.onclick_auto_build();
            for (i = 0; i < fields.length; i++) {
                field = Y.DOM.byId('field.' + fields[i]);
                Y.Assert.isFalse(
                    field.disabled, fields[i] + ' field disabled');
            }
            this.auto_build.checked = false;
            module.onclick_auto_build();
            for (i = 0; i < fields.length; i++) {
                field = Y.DOM.byId('field.' + fields[i]);
                Y.Assert.isTrue(
                    field.disabled, fields[i] + ' field not disabled');
            }
        }

    }));
}, '0.1', {
    requires: ['lp.testing.runner', 'test', 'test-console',
               'Event', 'node-event-simulate',
               'lp.snappy.snap.edit']
});
