/* Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Form overlay widgets and subscriber handling for bug pages.
 *
 * @module bugs
 * @submodule bugtask_index
 */

YUI.add('lp.bugs.bugtask_index', function(Y) {

var namespace = Y.namespace('lp.bugs.bugtask_index');

// Override for testing
namespace.ANIM_DURATION = 1;

// lazr.FormOverlay objects.
var duplicate_form_overlay;
var privacy_form_overlay;

// The url of the page used to update bug duplicates.
var update_dupe_url;

// The launchpad js client used.
var lp_client;

// The launchpad client entry for the current bug.
var lp_bug_entry;

// The bug itself, taken from cache.
var bug_repr;

// Overlay related vars.
var submit_button_html =
    '<button type="submit" name="field.actions.change" ' +
    'value="Change" class="lazr-pos lazr-btn" >OK</button>';
var cancel_button_html =
    '<button type="button" name="field.actions.cancel" ' +
    'class="lazr-neg lazr-btn" >Cancel</button>';
var privacy_link;
var privacy_spinner;
var link_branch_link;

namespace.setup_bugtask_index = function() {
    /*
     * Check the page for links related to overlay forms and request the HTML
     * for these forms.
     */
    Y.on('load', function() {
        if (Y.UA.ie) {
            return;
        }
        // If the user is not logged in, then we need to defer to the
        // default behaviour.
        if (LP.links.me === undefined) {
            return;
        }

        setup_client_and_bug();

        // Look for the 'Mark as duplicate' links or the
        // 'change duplicate bug' link.
        var update_dupe_link = Y.one(
            '.menu-link-mark-dupe, #change_duplicate_bug');

        if (update_dupe_link) {
            // First things first, pre-load the mark-dupe form.
            update_dupe_url = update_dupe_link.get('href');
            var mark_dupe_form_url = update_dupe_url + '/++form++';

            var form_header = '<p>Marking this bug as a duplicate will,' +
                              ' by default, hide it from search results ' +
                              'listings.</p>';

            var has_dupes = Y.one('#portlet-duplicates');
            if (has_dupes !== null) {
                form_header = form_header +
                    '<p style="padding:2px 2px 0 36px;" ' +
                    'class="large-warning"><strong>Note:</strong> ' +
                    'This bug has duplicates of its own. ' +
                    'If you go ahead, they too will become duplicates of ' +
                    'the bug you specify here.  This cannot be undone.' +
                    '</p></div>';
            }

            duplicate_form_overlay = new Y.lazr.FormOverlay({
                headerContent: '<h2>Mark bug report as duplicate</h2>',
                form_header: form_header,
                form_submit_button: Y.Node.create(submit_button_html),
                form_cancel_button: Y.Node.create(cancel_button_html),
                centered: true,
                form_submit_callback: update_bug_duplicate,
                visible: false
            });
            duplicate_form_overlay.render('#duplicate-form-container');
            duplicate_form_overlay.loadFormContentAndRender(
                mark_dupe_form_url);

            // Add an on-click handler to any links found that displays
            // the form overlay.
            update_dupe_link.on('click', function(e) {
                // Only go ahead if we have received the form content by the
                // time the user clicks:
                if (duplicate_form_overlay){
                    e.preventDefault();
                    duplicate_form_overlay.show();
                    Y.DOM.byId('field.duplicateof').focus();
                }
            });
            // Add a class denoting them as js-action links.
            update_dupe_link.addClass('js-action');
        }

        privacy_link = Y.one('#privacy-link');

        if (privacy_link) {
            var privacy_link_url = privacy_link.getAttribute('href') +
              '/++form++';
            var privacy_div = Y.one('#privacy-text');
            var privacy_html = privacy_link.get('innerHTML') + ' ';
            privacy_div.set('innerHTML', privacy_html);
            var privacy_text = Y.one('#privacy-text');
            privacy_link = Y.Node.create(
                '<a id="privacy-link" class="sprite edit" title="[edit]">' +
                '<span class="invisible-link">edit</span>&nbsp;</a>');
            privacy_link.set('href', privacy_link_url);
            privacy_text.appendChild(privacy_link);
            privacy_spinner = Y.Node.create(
                '<img src="/@@/spinner" style="display: none" />');
            privacy_text.appendChild(privacy_spinner);


            privacy_form_overlay = new Y.lazr.FormOverlay({
                headerContent: '<h2>Change privacy settings</h2>',
                form_submit_button: Y.Node.create(submit_button_html),
                form_cancel_button: Y.Node.create(cancel_button_html),
                centered: true,
                form_submit_callback: update_privacy_settings,
                visible: false
            });
            privacy_form_overlay.render('#privacy-form-container');
            privacy_form_overlay.loadFormContentAndRender(privacy_link_url);
            privacy_link.on('click', function(e) {
                if (privacy_form_overlay) {
                    e.preventDefault();
                    privacy_form_overlay.show();
                    // XXX Abel Deuring 2009-04-23, bug 365462
                    // Y.one('#field.private') returns null.
                    // Seems that YUI does not like IDs containing a '.'
                    document.getElementById('field.private').focus();
                }
            });
            privacy_link.addClass('js-action');
        }
        setup_add_attachment();
        setup_link_branch_picker();
        namespace.setup_load_comments(true);
    }, window);
};


/*
 * Create the lp client and bug entry if we haven't done so already.
 *
 * @method setup_client_and_bug
 */
function setup_client_and_bug() {
    lp_client = new Y.lp.client.Launchpad();

    if (bug_repr === undefined) {
        bug_repr = LP.cache.bug;
        lp_bug_entry = new Y.lp.client.Entry(
            lp_client, bug_repr, bug_repr.self_link);
    }
}

/*
 * Update the bug duplicate via the LP API
 */
function update_bug_duplicate(data) {
    // XXX noodles 2009-03-17 bug=336866 It seems the etag
    // returned by lp_save() is incorrect. Remove it for now
    // so that the second save does not result in a '412
    // precondition failed' error.
    //
    // XXX deryck 2009-04-29 bug=369293 Also, this has to
    // happen before *any* call to lp_save now that bug
    // subscribing can be done inline.  Named operations
    // don't return new objects, making the cached bug's
    // etag invalid as well.
    lp_bug_entry.removeAttr('http_etag');

    // Hide the formoverlay:
    duplicate_form_overlay.hide();

    // Hide the dupe edit icon if it exists.
    var dupe_edit_icon = Y.one('#change_duplicate_bug');
    if (dupe_edit_icon !== null) {
        dupe_edit_icon.setStyle('display', 'none');
    }

    // Add the spinner...
    var dupe_span = Y.one('#mark-duplicate-text');
    dupe_span.removeClass('sprite bug-dupe');
    dupe_span.addClass('update-in-progress-message');

    // Set the new duplicate link on the bug entry.
    var new_dup_url = null;
    var new_dup_id = Y.Lang.trim(data['field.duplicateof'][0]);
    if (new_dup_id !== '') {
        var self_link = lp_bug_entry.get('self_link');
        var last_slash_index = self_link.lastIndexOf('/');
        new_dup_url = self_link.slice(0, last_slash_index+1) + new_dup_id;
    }
    var old_dup_url = lp_bug_entry.get('duplicate_of_link');
    lp_bug_entry.set('duplicate_of_link', new_dup_url);

    // Create a config for the lp_save method
    config = {
        on: {
            success: function(updated_entry) {
                dupe_span.removeClass('update-in-progress-message');
                lp_bug_entry = updated_entry;

                if (new_dup_url !== null) {
                    dupe_span.set('innerHTML', [
                        '<a id="change_duplicate_bug" ',
                        'title="Edit or remove linked duplicate bug" ',
                        'class="sprite edit"></a>',
                        'Duplicate of <a>bug #</a>'].join(""));
                    dupe_span.all('a').item(0)
                        .set('href', update_dupe_url);
                    dupe_span.all('a').item(1)
                        .set('href', '/bugs/' + new_dup_id)
                        .appendChild(document.createTextNode(new_dup_id));
                    var has_dupes = Y.one('#portlet-duplicates');
                    if (has_dupes !== null) {
                        has_dupes.get('parentNode').removeChild(has_dupes);
                    }
                    show_comment_on_duplicate_warning();
                } else {
                    dupe_span.addClass('sprite bug-dupe');
                    dupe_span.set('innerHTML', [
                        '<a class="menu-link-mark-dupe js-action">',
                        'Mark as duplicate</a>'].join(""));
                    dupe_span.one('a').set('href', update_dupe_url);
                    hide_comment_on_duplicate_warning();
                }
                Y.lp.anim.green_flash({
                    node: dupe_span,
                    duration: namespace.ANIM_DURATION
                    }).run();
                // ensure the new link is hooked up correctly:
                dupe_span.one('a').on(
                    'click', function(e){
                        e.preventDefault();
                        duplicate_form_overlay.show();
                        Y.DOM.byId('field.duplicateof').focus();
                    });
            },
            failure: function(id, request) {
                dupe_span.removeClass('update-in-progress-message');
                if (request.status === 400) {
                    duplicate_form_overlay.showError(
                        new_dup_id + ' is not a valid bug number or' +
                        ' nickname.');
                } else {
                    duplicate_form_overlay.showError(request.responseText);
                }
                duplicate_form_overlay.show();

                // Reset the lp_bug_entry.duplicate_of_link as it wasn't
                // updated.
                lp_bug_entry.set('duplicate_of_link', old_dup_url);

            }
        }
    };

    // And save the updated entry.
    lp_bug_entry.lp_save(config);
}

/*
 * Ensure that a warning about adding a comment to a duplicate bug
 * is displayed.
 *
 * @method show_comment_on_duplicate_warning
 */
var show_comment_on_duplicate_warning = function() {
    var duplicate_warning = Y.one('#warning-comment-on-duplicate');
    if (duplicate_warning === null) {
        var container = Y.one('#add-comment-form');
        var first_node = container.get('firstChild');
        duplicate_warning = Y.Node.create(
            ['<div class="warning message"',
             'id="warning-comment-on-duplicate">',
             'Remember, this bug report is a duplicate. ',
             'Comment here only if you think the duplicate status is wrong.',
             '</div>'].join(''));
        container.insertBefore(duplicate_warning, first_node);
    }
};

/*
 * Ensure that no warning about adding a comment to a duplicate bug
 * is displayed.
 *
 * @method hide_comment_on_duplicate_warning
 */
var hide_comment_on_duplicate_warning = function() {
    var duplicate_warning = Y.one('#warning-comment-on-duplicate');
    if (duplicate_warning !== null) {
        duplicate_warning.ancestor().removeChild(duplicate_warning);
    }
};


var update_privacy_settings = function(data) {
    // XXX noodles 2009-03-17 bug=336866 It seems the etag
    // returned by lp_save() is incorrect. Remove it for now
    // so that the second save does not result in a '412
    // precondition failed' error.
    //
    // XXX deryck 2009-04-29 bug=369293 Also, this has to
    // happen before *any* call to lp_save now that bug
    // subscribing can be done inline.  Named operations
    // don't return new objects, making the cached bug's
    // etag invalid as well.
    lp_bug_entry.removeAttr('http_etag');

    privacy_form_overlay.hide();

    var privacy_text = Y.one('#privacy-text');
    var privacy_div = Y.one('#privacy');
    privacy_link.setStyle('display', 'none');
    privacy_spinner.setStyle('display', 'inline');

    if (lp_client === undefined) {
        lp_client = new Y.lp.client.Launchpad();
    }

    if (lp_bug_entry === undefined) {
        var bug_repr = LP.cache.bug;
        lp_bug_entry = new Y.lp.client.Entry(
            lp_client, bug_repr, bug_repr.self_link);
    }

    var private_flag = data['field.private'] !== undefined;
    var security_related =
        data['field.security_related'] !== undefined;

    lp_bug_entry.set('private', private_flag);
    lp_bug_entry.set('security_related', security_related);
    var error_handler = new Y.lp.client.ErrorHandler();
    error_handler.clearProgressUI = function () {
        privacy_spinner.setStyle('display', 'none');
        privacy_link.setStyle('display', 'inline');
    };
    error_handler.showError = function (error_msg) {
        Y.lp.anim.red_flash({
            node: privacy_div,
            duration: namespace.ANIM_DURATION
            }).run();
        privacy_form_overlay.showError(error_msg);
        privacy_form_overlay.show();
    };

    var base_url = LP.cache.context.web_link;
    var submit_url = base_url+"/+secrecy";
    var qs = Y.lp.client.append_qs('', 'field.actions.change', 'Change');
    qs = Y.lp.client.append_qs(qs, 'field.private', private_flag?'on':'off');
    qs = Y.lp.client.append_qs(
        qs, 'field.security_related', security_related?'on':'off');
    var sub_list_node = Y.one('#other-bug-subscribers');
    var subscribers_list = sub_list_node.getData('subscribers_loader');
    var config = {
        method: "POST",
        headers: {'Accept': 'application/xhtml'},
        data: qs,
        on: {
            start: function () {
                subscribers_list.subscribers_list.startActivity(
                    'Updating subscribers...');
            },
            end: function () {
                subscribers_list.subscribers_list.stopActivity();
            },
            success: function (id, response) {
                if (response.responseText !== '') {
                    var result_data = Y.JSON.parse(response.responseText);
                    var subscribers = result_data.subscription_data;
                    subscribers_list._loadSubscribersFromList(subscribers);
                    var cache_data = result_data.cache_data;
                    var item;
                    for (item in cache_data) {
                        if (cache_data.hasOwnProperty(item)) {
                            LP.cache[item] = cache_data[item];
                        }
                    }
                    var ns = Y.lp.bugs.bugtask_index.portlets.subscription;
                    ns.update_subscription_status();
                }
                privacy_spinner.setStyle('display', 'none');
                privacy_link.setStyle('display', 'inline');

                if (private_flag) {
                    Y.one('body').replaceClass('public', 'private');
                    privacy_div.replaceClass('public', 'private');
                    privacy_text.set(
                        'innerHTML',
                        'This report is <strong>private</strong> ');
                    Y.lp.app.privacy.display_privacy_notification();
                } else {
                    Y.one('body').replaceClass('private', 'public');
                    privacy_div.replaceClass('private', 'public');
                    privacy_text.set(
                        'innerHTML', 'This report is public ');
                    Y.lp.app.privacy.hide_privacy_notification();
                }
                privacy_text.appendChild(privacy_link);
                privacy_text.appendChild(privacy_spinner);

                var security_message = Y.one('#security-message');
                if (security_related) {
                    if (security_message === null) {
                        var security_message_html = [
                            '<div style="',
                            '    margin-top: 0.5em;',
                            '    padding-right: 18px;',
                            '    center right no-repeat;"',
                            '    class="sprite security"',
                            '    id="security-message"',
                            '>Security vulnerability</div>'
                        ].join('');
                        security_message = Y.Node.create(
                           security_message_html);
                        privacy_div.appendChild(security_message);
                    }
                } else {
                    if (security_message !== null) {
                        privacy_div.removeChild(security_message);
                    }
                }
                Y.lp.client.display_notifications(
                    response.getResponseHeader('X-Lazr-Notifications'));
                Y.lp.anim.green_flash({
                    node: privacy_div,
                    duration: namespace.ANIM_DURATION
                    }).run();
            },
            failure: error_handler.getFailureHandler()
        }
    };
    lp_client.io_provider.io(submit_url, config);
};

/**
 * Do a preemptive search for branches that contain the current bug's ID.
 */
function do_pre_search(picker, bug_id) {
    if (!Y.Lang.isValue(bug_id)) {
        bug_id = LP.cache.bug.id;
    }
    picker.set('footer_slot', 'Loading suggestions...');
    // A very few bugs have small IDs.
    var original_min_search_chars = picker.get('min_search_chars');
    picker.set('min_search_chars', 0);
    picker.fire('search', bug_id.toString(), undefined, true);
    // Don't disable the search input box or the search button while
    // doing our search.
    picker.set('search_mode', false);
    picker.set('min_search_chars', original_min_search_chars);
}
// Expose to the namespace for testing.
namespace._do_pre_search = do_pre_search;


/**
 * Set up the link-a-related-branch picker.
 */
function setup_link_branch_picker() {
    setup_client_and_bug();

    var error_handler = new Y.lp.client.ErrorHandler();

    error_handler.clearProgressUI = function () {
        link_branch_link.toggleClass('update-in-progress-message');
    };
    error_handler.showError = function(error_msg) {
        Y.lp.app.errors.display_error(
           Y.one('.menu-link-addbranch'), error_msg);
    };

    function get_branch_and_link_to_bug(data) {
        var branch_url = data.api_uri;
        config = {
            on: {
                success: link_branch_to_bug,
                failure: error_handler.getFailureHandler()
            }
        };

        // Start the spinner and then grab the branch.
        link_branch_link.toggleClass('update-in-progress-message');
        lp_client.get(branch_url, config);
    }

    // Set up the picker itself.
    link_branch_link = Y.one('.menu-link-addbranch');
    if (Y.Lang.isValue(link_branch_link)) {
        var config = {
            header: 'Link a related branch',
            step_title: 'Search',
            picker_activator: '.menu-link-addbranch'
        };

        config.save = get_branch_and_link_to_bug;
        var picker = Y.lp.app.picker.create('Branch', config);
        // When the user clicks on "Link a related branch" do a search for
        // branches that contain the bug number (but only once).
        link_branch_link.once('click', function (e) {
            do_pre_search(picker);
        });
    }
}

/**
 * Link a branch to the current bug.
 * @param branch {Object} The branch to link to the bug, as returned by
 *                        the Launchpad API.
 */
function link_branch_to_bug(branch) {
    var error_handler = new Y.lp.client.ErrorHandler();
    error_handler.clearProgressUI = function () {
        link_branch_link.toggleClass('update-in-progress-message');
    };
    error_handler.showError = function(error_msg) {
        Y.lp.app.errors.display_error(
           Y.one('.menu-link-addbranch'), error_msg);
    };

    // Call linkBranch() on the bug.
    config = {
        on: {
            success: function(bug_branch_entry) {
                link_branch_link.toggleClass(
                    'update-in-progress-message');

                // Grab the XHTML representation of the branch and add
                // it to the list of branches.
                config = {
                    on: {
                        success: function(branch_html) {
                            add_branch_to_linked_branches(branch_html);
                        }
                    },
                    accept: Y.lp.client.XHTML
                };
                lp_client.get(bug_branch_entry.get('self_link'), config);
            },
            failure: error_handler.getFailureHandler()
        },
        parameters: {
            branch: branch.get('self_link')
        }
    };
    lp_client.named_post(
        lp_bug_entry.get('self_link'), 'linkBranch', config);
}

/**
 * Add a branch to the list of linked branches.
 *
 * @param branch_html {Object} The branch html to add to the list of
 *                    linked branches, as returned by the Launchpad API.
 */
function add_branch_to_linked_branches(branch_html) {
    var anim;
    var bug_branch_node = Y.Node.create(branch_html);
    var bug_branch_list = Y.one('#bug-branches');
    if (!Y.Lang.isValue(bug_branch_list)) {
        bug_branch_list = Y.Node.create(
            '<div id="bug-branches">' +
            '  <h2>Related branches</h2>' +
            '</div>');

        var bug_branch_container = Y.one('#bug-branches-container');
        bug_branch_container.appendChild(bug_branch_list);
        anim = Y.lp.anim.green_flash({
            node: bug_branch_list,
            duration: namespace.ANIM_DURATION
            });
    } else {
        anim = Y.lp.anim.green_flash({
            node: bug_branch_node,
            duration: namespace.ANIM_DURATION
            });
    }

    var existing_bug_branch_node = bug_branch_list.one(
        '#' + bug_branch_node.getAttribute('id'));
    if (!Y.Lang.isValue(existing_bug_branch_node)) {
        // Only add the bug branch to the page if it isn't there
        // already.
        bug_branch_list.appendChild(bug_branch_node);
    } else {
        // If the bug branch exists already, flash it.
        anim = Y.lp.anim.green_flash({
            node: existing_bug_branch_node,
            duration: namespace.ANIM_DURATION
            });
    }
    anim.run();
    // Fire of the generic branch linked event.
    Y.fire('lp:branch-linked', bug_branch_node);
}

var status_choice_data = [];

var update_maybe_confirmed_status = function() {
    // This would be better done via client-side MVC for the pertinent
    // bugtasks, but we don't have that yet.
    Y.Array.each(
        status_choice_data,
        function(rowdata) {
            if (rowdata.widget.get('value') === 'New') {
                lp_client.get(
                    rowdata.config.bugtask_path,
                    // We will silently fail.
                    // This is not critical functionality.
                    {on: {success: function(bugtask) {
                        var status = bugtask.get('status');
                        if (status !== rowdata.widget.get('value')) {
                            rowdata.widget.set('value', status);
                            rowdata.widget.fire('save');
                        }
                    }}});
            }
        }
    );
};

/**
 * Set up the bug task table.
 *
 * Called once on load, to initialize the page, and also when the contents of
 * the bug task table is replaced after an XHR call.
 *
 * @method setup_bugtask_table
 */
namespace.setup_bugtask_table = function() {
    var bugtask_data = LP.cache.bugtask_data;
    if (!Y.Lang.isValue(bugtask_data)) {
        return;
    }
    var picker_connect = Y.namespace('lp.app.picker.connect');
    var process_link = function(link) {
        // The link may already have been processed.
        if (link.hasClass('js-action')) {
            return;
        }
        var func_name = link.get('id');
        var connect_func = picker_connect[func_name];
        if (Y.Lang.isFunction(connect_func)) {
            connect_func();
        }
    };
    var id;
    for (id in bugtask_data) {
        if (bugtask_data.hasOwnProperty(id)) {
            var conf = bugtask_data[id];
            var form_row = Y.one('#' + conf.form_row_id);
            // If there's associated expandable bugtask form for the bug task,
            // we need to wire up the target and assignee pickers.
            // This setup_bugtask_table() method is called when the page loads
            // as well as after replacing the table. On page load, the pickers
            // are wired by javascript embedded in the picker tales so we need
            // to ensure we handle this case.
            if( form_row !== null ) {
                form_row.all('a').each(process_link);
            }
            // Now wire up any other javascript widgets in the table row.
            namespace.setup_bugtask_row(conf);
        }
    }
};

/**
 * Show a spinner next to the delete icon.
 *
 * @method _showDeleteSpinner
 */
namespace._showDeleteSpinner = function(delete_link) {
    var spinner_node = Y.Node.create(
    '<img class="spinner" src="/@@/spinner" alt="Deleting..." />');
    delete_link.insertBefore(spinner_node, delete_link);
    delete_link.addClass('unseen');
};

/**
 * Hide the delete spinner.
 *
 * @method _hideDeleteSpinner
 */
namespace._hideDeleteSpinner = function(delete_link, show_link) {
    if( show_link ) {
        delete_link.removeClass('unseen');
    }
    var spinner = delete_link.get('parentNode').one('.spinner');
    if (spinner !== null) {
        spinner.remove();
    }
};

/**
 * Replace the currect bugtask table with a new one, ensuring all Javascript
 * widgets are correctly wired up.
 *
 * @method _render_bugtask_table
 */
namespace._render_bugtask_table = function(new_table) {
    var bugtask_table = Y.one('#affected-software');
    bugtask_table.replace(new_table);
    namespace.setup_bugtask_table();
};

/**
 * Prompt the user to confirm the deletion of the selected bugtask.
 * widgets are correctly wired up.
 *
 * @method _confirm_bugtask_delete
 */
namespace._confirm_bugtask_delete = function(delete_link, conf) {
    var delete_text_template = [
        '<p class="large-warning" style="padding:2px 2px 0 36px;">',
        '    You are about to mark bug "{bug}"<br>as no longer affecting',
        '    {target}.<br><br>',
        '    <strong>Please confirm you really want to do this.</strong>',
        '</p>'
        ].join('');
    var delete_text = Y.Lang.substitute(delete_text_template,
            {bug: conf.bug_title, target: conf.targetname});
    var co = new Y.lp.app.confirmationoverlay.ConfirmationOverlay({
        submit_fn: function() {
            namespace.delete_bugtask(delete_link, conf);
        },
        form_content: delete_text,
        headerContent: '<h2>Confirm bugtask deletion</h2>'
    });
    co.show();
};

/**
 * Redirect to a new URL. We need to break this out to allow testing.
 *
 * @method _redirect
 */
namespace._redirect = function(url) {
    window.location.replace(url);
};

/**
 * Process the result of the XHR request to delete a bugtask.
 *
 * @method _process_bugtask_delete_response
 */
namespace._process_bugtask_delete_response = function(
        response, bugtask_id, row_id, delete_link) {
    // The deleted row will fade out before being removed from the table.
    var animate_deletion = function(after_callback) {
        var row = Y.one('#' + row_id);
        row.setStyle('opacity', 1);
        row.addClass('transparent');
        var row_fade_out = new Y.Anim({
            node: row,
            to: {opacity: 0},
            duration: namespace.ANIM_DURATION
        });
        if( Y.Lang.isFunction(after_callback) ) {
            row_fade_out.on('end', after_callback);
        }
        row_fade_out.run();
    };

    // If the bugtask has already been deleted, the HTTP response status will
    // be 404. In this case, we remove the affected row and display a
    // informational message to the user.
    if( response.status === 404) {
        var message = Y.Lang.substitute(
            "Bug task affecting {targetname} has already been deleted.",
            {targetname: LP.cache.bugtask_data[bugtask_id].targetname});
        var notification = Y.Lang.substitute(
                '[[20, "{message}"]]', {message: message});
        Y.lp.client.display_notifications(notification);
        animate_deletion(function() {
            var tr = Y.one('#' + row_id);
            if( tr !== null ) {
                tr.remove(true);
            }
            delete LP.cache.bugtask_data[bugtask_id];
        });
        return;
    }

    // If the result is json, then we need to perform a redirect to a new
    // bugtask URL. This happens when the current bugtask is deleted and we
    // need to ensure all link URLS are correctly reset.
    var content_type = response.getResponseHeader('Content-type');
    if (content_type === 'application/json') {
        Y.lp.client.display_notifications(
            response.getResponseHeader('X-Lazr-Notifications'));
        var redirect = Y.JSON.parse(response.responseText);
        if( !Y.Lang.isValue(redirect) ) {
            namespace._hideDeleteSpinner(delete_link, false);
            return;
        }
        animate_deletion();
        namespace._redirect(redirect.bugtask_url);
        return;
    }
    // We have received HTML, so we replace the current bugtask table with a
    // new one.
    animate_deletion(function() {
        delete LP.cache.bugtask_data[bugtask_id];
        namespace._render_bugtask_table(response.responseText);
        Y.lp.client.display_notifications(
            response.getResponseHeader('X-Lazr-Notifications'));
    });
};

/**
 * Delete the bugtask defined by the delete_link using an XHR call.
 *
 * @method delete_bugtask
 */
namespace.delete_bugtask = function (delete_link, conf) {
    Y.lp.client.remove_notifications();
    var error_handler = new Y.lp.client.ErrorHandler();
    var module = this;
    error_handler.showError = Y.bind(function (error_msg) {
        namespace._hideDeleteSpinner(delete_link, true);
        Y.lp.app.errors.display_error(undefined, error_msg);
    }, this);
    error_handler.handleError = Y.bind(function(id, response) {
        if( response.status === 404 ) {
            module._process_bugtask_delete_response(
                    response, conf.id, conf.row_id, delete_link);
            return true;
        }
        return false;
    }, this);

    var submit_url = delete_link.get('href');
    var qs = Y.lp.client.append_qs(
        '', 'field.actions.delete_bugtask', 'Delete');
    var y_config = {
        method: "POST",
        headers: {'Accept': 'application/json; application/xhtml'},
        on: {
            start:
                Y.bind(namespace._showDeleteSpinner, namespace, delete_link),
            failure:
                error_handler.getFailureHandler(),
            success:
                function(id, response) {
                    namespace._process_bugtask_delete_response(
                            response, conf.id, conf.row_id, delete_link);
                }
        },
        data: qs
    };
    var io_provider = Y.lp.client.get_configured_io_provider(conf);
    io_provider.io(submit_url, y_config);
};

/**
 * Set up a bug task table row.
 *
 * Called once per row, on load, to initialize the page.
 *
 * @method setup_bugtasks_row
 */
namespace.setup_bugtask_row = function(conf) {
    if (Y.UA.ie) {
        return;
    }

    var tr = Y.one('#' + conf.row_id);
    var bugtarget_content = Y.one('#bugtarget-picker-' + conf.row_id);
    var status_content = tr.one('.status-content');
    var importance_content = tr.one('.importance-content');
    var assignee_content = Y.one('#assignee-picker-' + conf.row_id);
    var milestone_content = tr.one('.milestone-content');
    var delete_link = tr.one('.bugtask-delete');

    // Wire up the delete link.
    if (Y.Lang.isValue(LP.links.me) && Y.Lang.isValue(delete_link)
            && conf.user_can_delete) {
        delete_link.on('click', function (e) {
            e.preventDefault();
            namespace._confirm_bugtask_delete(delete_link, conf);
        });
    }

    // For some tasks, the row is just a placeholder and the status is tracked
    // in a separate series task. If there's no status_content widget, we know
    // this is one such row and we can bail out.
    if (status_content === null) {
        return;
    }

    if (Y.Lang.isValue(LP.cache.bug) &&
        Y.Lang.isValue(LP.cache.bug.duplicate_of_link)) {
        // If the bug is a duplicate, don't set the widget up and
        // cancel clicks on the edit links. Users most likely don't
        // want to edit the bugtasks.
        status_content.on('click', function(e) { e.halt(); });
        importance_content.on('click', function(e) { e.halt(); });
        return;
    }

    if ((LP.links.me !== undefined) &&
        (LP.links.me !== null))  {
        if (Y.Lang.isValue(bugtarget_content)) {
            if (conf.target_is_product) {
              var bugtarget_picker = Y.lp.app.picker.addPickerPatcher(
                        'Product',
                        conf.bugtask_path,
                        "target_link",
                        bugtarget_content.get('id'),
                        {"step_title": "Search projects",
                         "header": "Change project"});
            }
        }

        if (conf.user_can_edit_status) {
            var status_choice_edit = new Y.ChoiceSource({
                contentBox: status_content,
                value: conf.status_value,
                title: 'Change status to',
                items: conf.status_widget_items,
                elementToFlash: status_content.get('parentNode'),
                backgroundColor:
                    tr.hasClass('highlight') ? '#FFFF99' : '#FFFFFF'
            });
            status_choice_edit.showError = function(err) {
              Y.lp.app.errors.display_error(null, err);
            };
            status_choice_edit.on('save', function(e) {
                var cb = status_choice_edit.get('contentBox');
                Y.Array.each(conf.status_widget_items, function(item) {
                    if (item.value === status_choice_edit.get('value')) {
                        cb.addClass(item.css_class);
                    } else {
                        cb.removeClass(item.css_class);
                    }
                });
                // Set the inline form control's value, so that submitting
                // it won't override the value we just set.
                Y.one(document.getElementById(conf.prefix + '.status')).set(
                    'value', status_choice_edit.get('value'));
            });
            status_choice_edit.plug({
                fn: Y.lp.client.plugins.PATCHPlugin, cfg: {
                        patch: 'status',
                        resource: conf.bugtask_path}});
            status_choice_edit.render();
            status_choice_data.push(
                {widget: status_choice_edit, config: conf});
        }
        if (conf.user_can_edit_importance) {
            var importance_choice_edit = new Y.ChoiceSource({
                contentBox: importance_content,
                value: conf.importance_value,
                title: 'Change importance to',
                items: conf.importance_widget_items,
                elementToFlash: importance_content.get('parentNode'),
                backgroundColor:
                    tr.hasClass('highlight') ? '#FFFF99' : '#FFFFFF'
            });
            importance_choice_edit.showError = function(err) {
              Y.lp.app.errors.display_error(null, err);
            };
            importance_choice_edit.on('save', function(e) {
                var cb = importance_choice_edit.get('contentBox');
                Y.Array.each(conf.importance_widget_items, function(item) {
                    if (item.value === importance_choice_edit.get('value')) {
                        cb.addClass(item.css_class);
                    } else {
                        cb.removeClass(item.css_class);
                    }
                });
                // Set the inline form control's value, so that submitting
                // it won't override the value we just set.
                Y.one(document.getElementById(
                    conf.prefix + '.importance')).set(
                        'value', importance_choice_edit.get('value'));
            });
            importance_choice_edit.plug({
                fn: Y.lp.client.plugins.PATCHPlugin, cfg: {
                        patch: 'importance',
                        resource: conf.bugtask_path}});
            importance_choice_edit.render();
        }
    }

    if (Y.Lang.isValue(milestone_content) && conf.user_can_edit_milestone) {
        var milestone_choice_edit = new Y.NullChoiceSource({
            contentBox: milestone_content,
            value: conf.milestone_value,
            title: 'Target to milestone',
            items: conf.milestone_widget_items,
            elementToFlash: milestone_content.get('parentNode'),
            backgroundColor: tr.hasClass('highlight') ? '#FFFF99' : '#FFFFFF',
            clickable_content: false
        });
        milestone_choice_edit.showError = function(err) {
            Y.lp.app.errors.display_error(null, err);
        };
        milestone_choice_edit.plug({
            fn: Y.lp.client.plugins.PATCHPlugin, cfg: {
                    patch: 'milestone_link',
                    resource: conf.bugtask_path}});
        milestone_choice_edit.after('save', function() {
            var new_value = milestone_choice_edit.get('value');
            if (Y.Lang.isValue(new_value)) {
                // XXX Tom Berger 2009-08-25 Bug #316694:
                // This is a slightly nasty hack that saves us from the need
                // to have a more established way of getting the web URL of
                // an API object. Once such a solution is available we should
                // fix this.
                milestone_content.one('.value').setAttribute(
                    'href', new_value.replace('/api/devel', ''));
            }
            // Set the inline form control's value, so that submitting
            // it won't override the value we just set.
            var inline_combo = Y.one(
                document.getElementById(conf.prefix + '.milestone'));
            if (Y.Lang.isValue(inline_combo)) {
            inline_combo.set('value', null);
                Y.Array.each(
                   milestone_choice_edit.get('items'), function(item) {
                    if (item.value === milestone_choice_edit.get('value')) {
                        inline_combo.all('option').each(function(opt) {
                            if (opt.get('innerHTML') === item.name) {
                                opt.set('selected', true);
                            }
                        });
                    }
                });
            }
            // Force redrawing the UI
            milestone_choice_edit._uiClearWaiting();
        });
        milestone_content.one('.nulltext').on(
            'click',
            milestone_choice_edit.onClick,
            milestone_choice_edit);
        milestone_choice_edit.render();
    }
    if (Y.Lang.isValue(assignee_content) && conf.user_can_edit_assignee) {
        // A validation callback called by the picker when the user selects
        // an assignee. We check to see if an assignee is a contributor and if
        // they are not, the user is asked to confirm their selection.
        var validate_assignee = function(picker, value, save_fn, cancel_fn) {
            if (value === null || !Y.Lang.isValue(value.api_uri)) {
                if (Y.Lang.isFunction(save_fn)) {
                    save_fn();
                    return;
                }
            }

            var do_private_check_save = function () {
                Y.lp.app.picker.public_private_warning(
                    picker, value, save_fn, cancel_fn);
            };

            var assignee_uri = Y.lp.client.normalize_uri(value.api_uri);
            assignee_uri = Y.lp.client.get_absolute_uri(assignee_uri);
            var error_handler = new Y.lp.client.ErrorHandler();
            error_handler.showError = function(error_msg) {
                Y.lp.app.errors.display_error(null, error_msg);
            };

            var process_contributor_result = function(contributor_info) {
                var is_contributor = contributor_info.is_contributor;
                if (!is_contributor) {
                    // Handle assignment to non contributor
                    var person = Y.Escape.html(contributor_info.person_name);
                    var pillar = Y.Escape.html(contributor_info.pillar_name);
                    var yesno_content_template =
                        "<p>{person_name} did not previously have any " +
                        "assigned bugs in {pillar}.</p>" +
                        "<p>Do you really want to assign them to this bug?"+
                        "</p>";
                    var yesno_content = Y.Lang.substitute(
                            yesno_content_template,
                            {person_name: person, pillar: pillar});
                    Y.lp.app.picker.yesno_save_confirmation(
                            picker, yesno_content, "Assign", "Choose Again",
                            do_private_check_save, cancel_fn);
                } else {
                    if (Y.Lang.isFunction(save_fn)) {
                        do_private_check_save();
                    }
                }
            };

            var y_config =  {
                on: {
                    success: process_contributor_result,
                    failure: error_handler.getFailureHandler()
                },
                parameters: {
                    person: assignee_uri
                }
            };
            lp_client.named_get(
                    conf.bugtask_path, "getContributorInfo", y_config);
        };

        var step_title;
        if (conf.hide_assignee_team_selection) {
            step_title = null;
        } else {
            step_title =
                (conf.assignee_vocabulary === 'ValidAssignee') ?
                "Search for people or teams" :
                "Select a team of which you are a member";
        }
        var assignee_picker = Y.lp.app.picker.addPickerPatcher(
            conf.assignee_vocabulary,
            conf.bugtask_path,
            "assignee_link",
            assignee_content.get('id'),
            {"picker_type": "person",
             "vocabulary_filters": conf.assignee_vocabulary_filters,
             "step_title": step_title,
             "header": "Change assignee",
             "selected_value": conf.assignee_value,
             "selected_value_metadata": conf.assignee_is_team?"team":"person",
             "assign_me_text": "Assign me",
             "remove_person_text": "Remove assignee",
             "remove_team_text": "Remove assigned team",
             "null_display_value": "Unassigned",
             "show_remove_button": conf.user_can_unassign,
             "show_assign_me_button": true,
             "validate_callback": validate_assignee});
        // Ordinary users can select only themselves and their teams.
        // Do not show the team selection, if a user is not a member
        // of any team,
        if (conf.hide_assignee_team_selection) {
            content_box = assignee_picker.get('contentBox');
            search_box = content_box.one('.yui3-picker-search-box');
            search_box.setStyle('display', 'none');
            var info = Y.Node.create('<p style="padding-top: 1em;"></p>')
                .set('text', 'You may only assign yourself because you are ' +
                'not affiliated with this project and do not have any team ' +
                'memberships.');
            search_box.insert(info, search_box);
        }
        assignee_picker.render();
    }

    // Set-up the expander on the bug task summary row.
    var icon_node = Y.one('tr#' + conf.row_id + ' a.bugtask-expander');
    var row_node = Y.one('tr#' + conf.form_row_id);
    if (Y.Lang.isValue(row_node)) {
        // When no row is present, this is bug task on a project with
        // multiple per-series tasks, so we do not need to set
        // the expander for the descriptive parent project task.
        var content_node = row_node.one('td form');
        var expander = new Y.lp.app.widgets.expander.Expander(
            icon_node, row_node, { animate_node: content_node });
        expander.setUp();
    }
};

/**
 * Set up the "me too" selection.
 *
 * Called once, on load, to initialize the page. Call this function if
 * the "me too" information is displayed on a bug page and the user is
 * logged in.
 *
 * @method setup_me_too
 */
namespace.setup_me_too = function(user_is_affected, others_affected_count) {
    // IE (7 & 8 tested) is stupid, stupid, stupid.
    if (Y.UA.ie) {
        return;
    }
    var me_too_content = Y.one('#affectsmetoo');
    var me_too_edit = new MeTooChoiceSource({
        contentBox: me_too_content, value: user_is_affected,
        elementToFlash: me_too_content,
        editicon: ".dynamic img.editicon",
        others_affected_count: others_affected_count
    });
    me_too_edit.render();
};

/**
 * This class is a derivative of ChoiceSource that handles the
 * specifics of editing "me too" option.
 *
 * @class MeTooChoiceSource
 * @extends ChoiceSource
 * @constructor
 */
function MeTooChoiceSource() {
    MeTooChoiceSource.superclass.constructor.apply(this, arguments);
}

MeTooChoiceSource.NAME = 'metoocs';
MeTooChoiceSource.NS = 'metoocs';

MeTooChoiceSource.ATTRS = {
    /**
     * The title is always the same, so bake it in here.
     *
     * @attribute title
     * @type String
     */
    title: {
        value: 'Does this bug affect you?'
    },

    /**
     * The items are always the same, so bake them in here.
     *
     * @attribute items
     * @type Array
     */
    items: {
        value: [
            { name: 'Yes, it affects me',
              value: true, disabled: false },
            { name: "No, it doesn't affect me",
              value: false, disabled: false }
        ]
    },

    /**
     * The number of other users currently affected by this bug.
     *
     * @attribute others_affected_count
     * @type Number
     */
    others_affected_count: {
        value: null
    }
};

// Put this in the bugs namespace so it can be accessed for testing.
namespace._MeTooChoiceSource = MeTooChoiceSource;

Y.extend(MeTooChoiceSource, Y.ChoiceSource, {
    initializer: function() {
        var widget = this;
        this.error_handler = new Y.lp.client.ErrorHandler();
        this.error_handler.clearProgressUI = function() {
            widget._uiClearWaiting();
        };
        this.error_handler.showError = function(error_msg) {
            widget.showError(error_msg);
        };
        // Set source_names.
        var others_affected_count = this.get('others_affected_count');
        var source_names = this._getSourceNames(others_affected_count);
        Y.each(this.get('items'), function(item) {
            if (source_names.hasOwnProperty(item.value)) {
                item.source_name = source_names[item.value];
            }
        });
    },

    /*
     * The results of _getSourceNames() should closely mirror the
     * results of BugTasksAndNominationsView.affected_statement and
     * anon_affected_statement.
     */
    _getSourceNames: function(others_affected_count) {
        var source_names = {};
        // What to say when the user is marked as affected.
        if (others_affected_count === 1) {
            source_names[true] = (
                'This bug affects you and 1 other person');
        }
        else if (others_affected_count > 1) {
            source_names[true] = (
                'This bug affects you and ' +
                others_affected_count + ' other people');
        }
        else {
            source_names[true] = 'This bug affects you';
        }
        // What to say when the user is marked as not affected.
        if (others_affected_count === 1) {
            source_names[false] = (
                'This bug affects 1 person, but not you');
        }
        else if (others_affected_count > 1) {
            source_names[false] = (
                'This bug affects ' + others_affected_count +
                ' people, but not you');
        }
        else {
            source_names[false] = "This bug doesn't affect you";
        }
        return source_names;
    },

    showError: function(err) {
        Y.lp.app.errors.display_error(null, err);
    },

    render: function() {
        MeTooChoiceSource.superclass.render.apply(this, arguments);
        // Force the ChoiceSource to be rendered inline.
        this.get('boundingBox').setStyle('display', 'inline');
        // Hide the static content and show the dynamic content.
        this.get('contentBox').one('.static').addClass('unseen');
        this.get('contentBox').one('.dynamic').removeClass('unseen');
    },

    _saveData: function() {
        // Set the widget to the 'waiting' state.
        this._uiSetWaiting();

        var value = this.getInput();
        var client =  new Y.lp.client.Launchpad();
        var widget = this;

        var config = {
            on: {
                success: function(entry) {
                    widget._uiClearWaiting();
                    MeTooChoiceSource.superclass._saveData.call(
                        widget, value);
                    if (value && widget.get('others_affected_count') > 0) {
                        // If we increased the affected count to 2 or more,
                        // maybe update the statuses of our bugtasks.
                        update_maybe_confirmed_status();
                    }
                },
                failure: this.error_handler.getFailureHandler()
            },
            parameters: {
                affected: value
            }
        };

        client.named_post(
            LP.cache.bug.self_link, 'markUserAffected', config);
    }
});
/*
 * Click handling to pass comment text to the attachment
 * page if there is a comment.
 *
 * @method setup_add_attachment
 */
function setup_add_attachment() {
    // Find zero or more links to modify.
    var attachment_link = Y.all('.menu-link-addcomment');
    attachment_link.on('click', function(e) {
        var comment_input = Y.one('[id="field.comment"]');
        if (comment_input.get('value') !== '') {
            var current_url = attachment_link.getAttribute('href');
            var attachment_url = current_url + '?field.comment=' +
                encodeURIComponent(comment_input.get('value'));
            attachment_link.setAttribute('href', attachment_url);
        }
    });
}

/**
 * Load more comments
 * @method load_more_comments
 * @param batched_comments_url {String} The URL from which to load
 *        comments.
 * @param comments_container {Node} The Node into which to place the
 *        comments.
 */
namespace.load_more_comments = function(batched_comments_url,
                                        comments_container,
                                        io_provider) {
    var spinner = Y.Node.create(
        '<img src="/@@/spinner" style="text_align: center; ' +
        'display: none" />');
    var spinner_span = Y.one('#more-comments-spinner');
    spinner_span.setStyle('display', 'inline');
    var handlers = {
        success: function(transactionid, response, args) {
            var new_comments_node =
                Y.Node.create("<div></div>");
            new_comments_node.set(
                'innerHTML', response.responseText);
            comments_container.setStyle('display', 'block');
            spinner_span.setStyle('display', 'none');
            comments_container.appendChild(new_comments_node);
            if (Y.Lang.isValue(Y.lp.anim)) {
                var success_anim = Y.lp.anim.green_flash(
                    {node: new_comments_node,
                    duration: namespace.ANIM_DURATION});
                success_anim.run();
            }
            batch_url_div = Y.one('#next-batch-url');
            if (Y.Lang.isValue(batch_url_div)) {
                batched_comments_url = batch_url_div.get(
                    'innerHTML');
                batch_url_div.remove();
                namespace.load_more_comments(
                    batched_comments_url, comments_container, io_provider);
            } else {
                // Remove the comments-hidden messages to avoid
                // confusion.
                Y.each(Y.all('.comments-hidden-message'), function(message) {
                    message.remove();
                });
                // Show the comment form, if available.
                var comment_form_container = Y.one(
                    '#add-comment-form-container');
                if (Y.Lang.isValue(comment_form_container)) {
                    comment_form_container.toggleClass('hidden');
                }
            }
        }
    };
    if (!Y.Lang.isValue(io_provider)) {
        io_provider = Y.lp.client.get_configured_io_provider();
    }
    var request = io_provider.io(batched_comments_url, {on: handlers});
};

/**
 * Set up the click handling for a single show-more-comments link.
 *
 * @method setup_show_more_comments_link
 * @param link {Node} The link to set up.
 * @param url {Object} The current batched_comments_url
 * @param container {Node} The node into which to load the comments.
 */
namespace.setup_show_more_comments_link = function(link, url, container) {
    link.on('click', function(e) {
        e.preventDefault();
        namespace.load_more_comments(url, container);
    });
    link.addClass('js-action');
};

/**
 *  Set up click handling to load the rest of the comments for the bug
 *  via javascript.
 *
 * @method setup_load_comments
 * @param load_more_comments {Boolean} If True, load_more_comments will
 *        be called immediately.
 */
namespace.setup_load_comments = function(load_more_comments) {
    var comments_container = Y.one('#comments-container');
    if (Y.Lang.isValue(comments_container)) {
        var current_offset = LP.cache.initial_comment_batch_offset;
        var batched_comments_url =
            LP.cache.context.self_link.replace('/api/devel', '') +
            "/+batched-comments?offset=" +
            current_offset;
        // Set up the show more comments links to be JSified. This gives
        // us a fallback should the initial load_more_comments call fail
        // for some reason, rather than leaving the user without any way
        // to view all the comments.
        var show_comments_links = Y.all('.show-comments-link');
        if (show_comments_links) {
            Y.each(show_comments_links, function(link) {
                namespace.setup_show_more_comments_link(
                    link, batched_comments_url, comments_container);
            });
        }
        if (load_more_comments === true) {
            namespace.load_more_comments(
                batched_comments_url, comments_container);
        }
    }
};


}, "0.1", {"requires": ["base", "oop", "node", "event", "io-base",
                        "json-parse", "substitute", "widget-position-ext",
                        "lazr.formoverlay", "lp.anim", "lazr.base",
                        "lazr.overlay", "lazr.choiceedit", "lp.app.picker",
                        "lp.bugs.bugtask_index.portlets.subscription",
                        "lp.app.widgets.expander", "lp.client", "escape",
                        "lp.client.plugins", "lp.app.errors",
                        "lp.app.privacy", "lp.app.confirmationoverlay"]});
