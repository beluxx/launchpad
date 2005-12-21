# Copyright 2004-2005 Canonical Ltd.  All rights reserved.

"""This module is used by the Launchpad webapp to determine titles for pages.

See https://wiki.launchpad.canonical.com/LaunchpadTitles

This module contains string or unicode literals assigned to names, or functions
such as this one:

  def bug_index(context, view):
      return 'Bug %s: %s' % (context.id, context.title)

The names of string or unicode literals and functions are the names of
the page templates, but with hyphens changed to underscores.  So, the function
bug_index given about is for the page template bug-index.pt.

If the function needs to include details from the request, this is available
from view.request.  However, these functions should not access view.request.
Instead, the view class should make a function or attribute available that
provides the required information.

If the function returns None, it means that the default page title for the
whole of Launchpad should be used.  This is defined in the variable
DEFAULT_LAUNCHPAD_TITLE.

Note that there are shortcuts for some common substitutions at the top of this
module.

The strings and functions for page titles are arranged in alphabetical order
after the helpers.

"""
__metaclass__ = type

from zope.component import getUtility
from canonical.launchpad.interfaces import (
    IProduct, IDistribution, IDistroRelease, ILaunchBag)

DEFAULT_LAUNCHPAD_TITLE = 'Launchpad'

# Helpers.

class BugPageTitle:
    def __call__(self, context, view):
        return "Bug #%d - %s" % (context.id, context.title)


class BugTaskPageTitle:
    def __call__(self, context, view):
        return "Bug #%d in %s - %s" % (
            context.bug.id, context.targetname, context.bug.title)


class BugTaskTargetingTitle:
    def __call__(self, context, view):
        return "Bug #%d in %s - Target Fix to Releases" % (
            context.bug.id, context.targetname)


class SubstitutionHelper:
    def __init__(self, text):
        self.text = text

    def __call__(self, context, view):
        raise NotImplementedError


class ContextDisplayName(SubstitutionHelper):
    def __call__(self, context, view):
        return self.text % context.displayname


class ContextId(SubstitutionHelper):
    def __call__(self, context, view):
        return self.text % context.id


class ContextTitle(SubstitutionHelper):
    def __call__(self, context, view):
        return self.text % context.title


class ContextBrowsername(SubstitutionHelper):
    def __call__(self, context, view):
        return self.text % context.browsername


class LaunchbagBugID(SubstitutionHelper):
    def __call__(self, context, view):
        return self.text % getUtility(ILaunchBag).bug.id


# Functions and strings used as the titles of pages.

attachment_index = ContextTitle('Malone Bug Attachment: %s')

attachments_index = 'Malone Bug Attachments'

bazaar_index = 'The Launchpad Bazaar'

bazaar_sync_review = 'Review upstream repositories for Launchpad Bazaar syncing'

def binarypackagerelease_index(context, view):
    return "%s binary package in Launchpad" % context.title

binarypackagenames_index = 'Binary package name set'

bounties_index = 'Launchpad Bounty Tracker'

bounty_add = 'Register a New Bounty in Launchpad'

bounty_edit = ContextTitle('Edit Bounty: %s')

bounty_add = 'Register a bounty in Launchpad'

bounty_link = ContextTitle('Link a bounty to %s')

bounty_edit = ContextTitle('Edit bounty "%s"')

bounty_index = ContextTitle('Launchpad Bounty: %s')

bounty_subscription = 'Bounty Subscription'

branch_edit = 'Edit Branch Details'

branch_index = ContextTitle('Bazaar Branch: %s')

branch_subscription = ContextTitle('Subscription to Branch %s')

branchtarget_branches = ContextTitle('Branches for %s')

bug_activity = ContextId('Bug #%s - Activity Log')

def bug_add(context, view):
    # XXX, Brad Bollenbach, 2005-07-15: This is a hack until our fancy
    # new page title machinery allows for two different pages that use
    # the same template to have different titles (the way ZCML does.)
    # See https://launchpad.ubuntu.com/malone/bugs/1376
    product_context = IProduct(context, None)
    distro_context = IDistribution(context, None)
    distrorelease_context = IDistroRelease(context, None)

    if product_context or distro_context or distrorelease_context is not None:
        context_title = ContextTitle('Report a bug about %s')
        return context_title(context, view)
    else:
        return "Report a bug"

bug_addsubscriber = LaunchbagBugID("Bug #%d - Add Subscriber")

bug_attachment_add = LaunchbagBugID('Bug #%d - Add an Attachment')

def bug_attachment_edit(context, view):
    return 'Bug #%d - Edit Attachment (%s)' % (
        context.bug.id, context.title)

bug_attachments = ContextId('Malone Bug Attachments for Bug #%s')

bug_cve = LaunchbagBugID("Bug #%d - Add CVE Reference")

bug_edit = BugPageTitle()

bug_extref_add = LaunchbagBugID("Bug #%d - Add External Web Link")

def bug_extref_edit(context, view):
    return 'Bug #%d - Edit External Web Link (%s)' % (
        context.bug.id, context.title)

bug_index = BugPageTitle()

bug_mark_as_duplicate = ContextId('Bug #%d - Mark as Duplicate')

bug_removecve = LaunchbagBugID("Bug #%d - Remove CVE Reference")

bug_secrecy = ContextId('Set secrecy for bug #%s')

bug_secrecy = ContextId('Bug #%d - Set Bug Secrecy')

bug_subscription = ContextId('Subscribe or unsubscribe from Bug #%s')

bug_watch_add = LaunchbagBugID('Bug #%d - Add an External Bug Watch')

buglisting_advanced = ContextTitle("Bugs in %s")

buglisting_default = ContextTitle("Bugs in %s")

def bugwatch_editform(context, view):
    return 'Bug #%d - Edit an External Bug Watch (%s in %s)' % (
        context.bug.id, context.remotebug, context.bugtracker.title)

# bugpackageinfestations_index is a redirect

# bugproductinfestations_index is a redirect

def bugs_assigned(context, view):
    if view.user:
        return 'Bugs assigned to %s' % view.user.browsername
    else:
        return 'No-one to display bugs for'

bugs_createdby_index = 'Malone Bug Report by Creator'

bugs_index = 'Malone Master Bug List'

bugtask_index = BugTaskPageTitle()

bugtask_release_targeting = BugTaskTargetingTitle()

bugtask_view = BugTaskPageTitle()

bugtask_edit = BugTaskPageTitle()

# bugtask_macros_buglisting contains only macros
# bugtasks_index is a redirect

bugtracker_edit = ContextTitle('Edit %s Details')

bugtracker_index = ContextTitle('Malone Bugtracker: %s')

bugtrackers_add = 'Register External Bugtracker in Malone'

bugtrackers_index = 'Malone-Registered Bug Trackers'

build_buildlog = ContextTitle('%s: Build Log')

build_changes = ContextTitle('%s: Changes')

build_index = ContextTitle('%s: Overview')

builders = 'Launchpad Build Farm Overview'

builder_edit = ContextTitle('Editing %s details')

builder_index = ContextTitle('%s Overview')

builder_cancel = ContextTitle('Cancel %s Job')

builder_mode = ContextTitle('Change %s Mode')

calendar = ContextTitle('%s')

calendar_index = ContextTitle('%s')

calendar_event_addform = ContextTitle('Add Event to Calendar "%s"')

calendar_event_display = ContextTitle('Event "%s"')

calendar_event_editform = ContextTitle('Edit Event "%s"')

calendar_subscribe = ContextTitle('Subscribe to "%s"')

calendar_subscriptions = 'Calendar Subscriptions'

def calendar_view(context, view):
    return '%s - %s' % (context.calendar.title, view.datestring)
calendar_view_day = calendar_view
calendar_view_week = calendar_view
calendar_view_month = calendar_view
calendar_view_year = calendar_view

codeofconduct_admin = 'Administer codes of conduct in Launchpad'

codeofconduct_index = ContextTitle('%s')

codeofconduct_list = 'Codes of Conduct in Launchpad'

cveset_all = 'All CVE Entries Registered in the Launchpad'

cveset_index = 'Launchpad CVE Tracker'

cve_index = ContextDisplayName('%s')

cve_bug = ContextDisplayName('Link %s to a Malone  Bug')

cve_removebug = ContextDisplayName('Remove Link between %s and Malone Bug')

debug_error = 'Launchpad - Error Debug Page'

debug_root_changelog = 'Launchpad Changelog'

debug_root_index = 'Launchpad Debug Home Page'

debug_unauthorized = 'Launchpad - Not Permitted'

default_editform = 'Default "Edit" Page'

distribution_allpackages = ContextTitle('All packages in %s')

distribution_cvereport = ContextTitle('CVE Reports for %s')

distribution_members = ContextTitle('%s distribution members')

distribution_memberteam = ContextTitle("Change %s's distribution team")

distribution_translations = ContextDisplayName('Translating %s')

distribution_translators = 'Appoint Distribution Translation Group'

distribution_search = ContextDisplayName('Search Packages in %s')

distribution_index = ContextTitle('%s in Launchpad')

distribution_builds = ContextTitle('%s Builds')

distributionsourcepackage_bugs = ContextTitle('Bugs in %s')

distributionsourcepackage_index = ContextTitle('%s')

distributionsourcepackagerelease_index = ContextTitle('%s')

distro_add = 'Adding New Distribution'

distro_edit = 'Create a new Distribution in Launchpad'

# distro_sources.pt.OBSELETE
# <title metal:fill-slot="title"><span tal:replace="context/title" />: Source
# Packages</title>

distroarchrelease_admin = ContextTitle('Administer %s')

distroarchrelease_index = ContextTitle('%s overview')

distroarchrelease_builds = ContextTitle('Builds for %s')

distroarchrelease_search = 'Binary Package Search'

distroarchreleasebinarypackage_index = ContextTitle('%s')

distroarchreleasebinarypackagerelease_index = ContextTitle('%s')

distrorelease_addport = ContextTitle('Add Port for %s')

distrorelease_bugs = ContextTitle('Release %s: Bugs')

distrorelease_cvereport = ContextDisplayName('CVE Report for %s')

def distrorelease_index(context, view):
    return '%s: %s' % (context.distribution.title, context.title)

distrorelease_packaging = ContextDisplayName('Mapping packages to upstream '
    'for %s')

distrorelease_search = ContextDisplayName('Search Packages in %s')

distrorelease_translations = ContextTitle('Translation of %s')

distrorelease_builds = ContextTitle('Builds for %s')

distroreleasebinarypackage_index = ContextTitle('%s')

distroreleaselanguage = ContextTitle('%s')

distroreleasesourcepackagerelease_index = ContextTitle('%s')

distros_index = 'Overview of Distributions in Launchpad'


errorservice_config = 'Configure Error Log'

errorservice_entry = 'View Error Log Report'

errorservice_index = 'View Error Log Report'

errorservice_tbentry = 'Traceback Entry'

foaf_about = 'About FOAF'

foaf_dashboard = 'Your Launchpad Dashboard'

foaf_index = 'Foaf Home Page'

foaf_mergerequest_sent = 'Merge User Accounts'

foaf_newteam = 'FOAF: Create a new Team'

foaf_requestmerge_multiple = 'Merge User Accounts'

foaf_requestmerge = 'Merge User Accounts'

foaf_todo = 'To-Do List'

karmaaction_index = 'Karma Actions'

karmaaction_edit = 'Edit Karma Action'

# launchpad_debug doesn't need a title.

def launchpad_addform(context, view):
    # Returning None results in the default Launchpad page title being used.
    return getattr(view, 'page_title', None)

launchpad_editform = launchpad_addform

launchpad_feedback = 'Help us improve Launchpad'

launchpad_forbidden = 'Forbidden'

launchpad_forgottenpassword = 'Forgot Your Launchpad Password?'

template_form = 'XXX PLEASE DO NOT USE TEMPLATE XXX'

launchpad_join = 'Join the Launchpad'

# launchpad_css is a css file

# launchpad_js is standard javascript

# XXX: The general form is a fallback form; I'm not sure why it is
# needed, nor why it needs a pagetitle, but I can't debug this today.
#   -- kiko, 2005-09-29
launchpad_generalform = "Launchpad - General Form (Should Not Be Displayed)"

launchpad_legal = 'Launchpad - Legalese'

launchpad_login = 'Log in or register with Launchpad'

launchpad_log_out = 'Log out from Launchpad'

launchpad_notfound = 'Launchpad Page Not Found'

launchpad_oops = 'System Error'

launchpad_requestexpired = 'Request Took Too Long'

# launchpad_widget_macros doesn't need a title.

logintoken_index = 'Launchpad: redirect to the logintoken page'

logintoken_mergepeople = 'Merge User Accounts'

logintoken_newaccount = 'Create a New Launchpad Account'

logintoken_resetpassword = 'Forgotten your Password?'

logintoken_validateemail = 'Validate email address'

logintoken_validategpg = 'Validate GPG Key'

logintoken_validatesignonlygpg = 'Validate Sign-Only GPG Key'

logintoken_validateteamemail = 'Validate email address'

# main_template has the code to insert one of these titles.

malone_about = 'About Malone'

malone_dashboard = 'Malone Dashboard'

malone_distros_index = 'File a Bug in a Distribution'

malone_index = 'Malone: Collaborative Open Source Bug Management'

# malone_people_index is a redirect

# malone_template is a means to include the mainmaster template

malone_to_do = 'Malone ToDo'

# messagechunk_snippet is a fragment

# messages_index is a redirect

message_add = ContextId('Bug #%d - Add a Comment')

milestone_add = ContextDisplayName('Add Milestone for %s')

milestone_index = ContextTitle('%s')

milestone_edit = ContextTitle('Edit %s')

no_app_component_yet = 'Missing App Component'

no_page_yet = 'Missing Page'

no_url_yet = 'No url for this yet'

# object_pots is a fragment.

object_potemplatenames = ContextDisplayName('Template names for %s')

object_reassignment = ContextTitle('Reassign %s')

def package_bugs(context, view):
    return 'Package Bug Listing for %s' % context.name

package_search = 'Package Search'

packages_bugs = 'Packages With Bugs'

people_index = 'Launchpad People'

people_list = 'People registered with Launchpad'

person_assignedbugs = ContextDisplayName('Bugs Assigned To %s')

person_bounties = ContextDisplayName('Bounties for %s')

person_branch_add = ContextDisplayName('Register a new branch for %s')

person_changepassword = 'Change your password'

person_codesofconduct = ContextDisplayName('%s Signed Codes of Conduct')

person_edit = ContextDisplayName('Edit %s Information')

person_editemails = ContextDisplayName('Edit %s Email Addresses')

person_editgpgkeys = ContextDisplayName('%s GPG Keys')

person_edithomepage = ContextDisplayName('Edit %s Home Page')

person_editircnicknames = ContextDisplayName('%s IRC Nicknames')

person_editjabberids = ContextDisplayName('%s Jabber IDs')

person_editsshkeys = ContextDisplayName('%s SSH Keys')

person_editwikinames = ContextDisplayName('%s Wiki Names')

# person_foaf is an rdf file

person_images = ContextDisplayName('%s Hackergotchi and Emblem')

person_index = ContextDisplayName('%s: Launchpad Overview')

person_karma = ContextDisplayName('Karma for %s')

person_packages = ContextDisplayName('Packages Maintained By %s')

person_packagebugs = ContextDisplayName('Bugs on Software Maintained by %s')

person_reportedbugs = ContextDisplayName('Bugs Reported By %s')

person_review = ContextDisplayName("Review %s' Information")

person_subscribedbugs = ContextDisplayName('Bugs %s is subscribed to')

person_translations = ContextDisplayName('Translations Made By %s')

person_teamhierarchy = ContextDisplayName('Team hierarchy for %s')

pofile_edit = 'Rosetta: Edit PO file details'

pofile_export = ContextTitle('%s file exports')

def pofile_index(context, view):
    return 'Rosetta: %s: %s' % (
        context.potemplate.title, context.language.englishname)

def pofile_translate(context, view):
    return 'Translating %s into %s with Rosetta' % (
        context.potemplate.displayname,
        context.language.englishname)

pofile_upload = ContextTitle('%s upload in Rosetta')

# portlet_* are portlets

poll_edit = ContextTitle('Edit poll %s')

poll_index = ContextTitle('%s')

poll_newoption = ContextTitle('Create a new Option in poll %s')

def poll_new(context, view):
    return 'Create a new Poll in team %s' % context.team.displayname

def polloption_edit(context, view):
    return 'Edit option: %s' % context.title

poll_options = ContextTitle('Options of Poll: %s')

poll_vote_condorcet = ContextTitle('Vote on: %s')

poll_vote_simple = ContextTitle('Vote on: %s')

potemplate_add = 'Add a new template to Rosetta'

# potemplate_chart is a fragment

potemplate_edit = ContextTitle('%s edit in Rosetta')

potemplate_index = ContextTitle('%s in Rosetta')

potemplate_upload = ContextTitle('%s upload in Rosetta')

potemplate_export = ContextTitle('Export %s\'s translations')

potemplatename_add = 'Add a new template name to Rosetta'

potemplatename_edit = ContextTitle('%s edit in Rosetta')

potemplatename_index = ContextTitle('%s in Rosetta')

potemplatenames_index = 'Template names in Launchpad'

product_add = 'Register a product with Launchpad'

product_bugs = ContextDisplayName('%s upstream bug reports')

product_branches = ContextDisplayName('%s\'s code branches in Launchpad')

product_distros = ContextDisplayName('%s packages: Comparison of distributions')

product_edit = ContextTitle('Edit Upstream Details: %s')

product_index = ContextTitle('Product: %s')

product_packages = ContextDisplayName('Packages of %s')

product_translations = ContextTitle('Rosetta Translations for %s')

def productrelease(context, view):
    return 'Details of %s %s' % (
        context.product.displayname, context.version)

def productrelease_edit(context, view):
    return 'Edit Details for %s %s' % (
        context.product.displayname, context.version)

productrelease_add = ContextTitle('Register a new release of %s')

productseries_translations = ContextTitle(
    'Rosetta Translation Templates for %s')

productseries_ubuntupkg = 'Ubuntu Source Package'

products_index = 'Launchpad Product / Applications Registry'

products_search = 'Launchpad: Advanced Upstream Product Search'

productseries_source = 'Add Source Import'

productseries_sourceadmin = 'Add Source Import'

productseries_translations_upload = 'Request New Translations Upload'

project = ContextTitle('Upstream Project: %s')

project_branches = ContextTitle('Bazaar Summary for %s')

project_bugs = ContextTitle('Malone Bug Summary for %s')

project_edit = ContextTitle('Edit "%s" Details')

project_index = ContextTitle('Project: %s')

project_interest = 'Rosetta: Project not translatable'

project_rosetta_index = ContextTitle('Rosetta: %s')

projects_index = 'Launchpad project registry'

projects_request = 'Rosetta: Request a project'

projects_search = 'Launchpad: Advanced Upstream Project Search'

rdf_index = "Launchpad RDF"

# redirect_up is a redirect

def reference_index(context, view):
    return 'Web References for Malone Bug # %s' % context.bug.id

# references_index is a redirect

registry_about = 'About the Launchpad Registry'

registry_dashboard = 'Launchpad Project & Product Dashboard'

registry_index = 'Project and Product Registration in Launchpad'

registry_listall = 'Launchpad: Complete List'

registry_review = 'Launchpad Content Review'

registry_to_do = 'Launchpad To-Do List'

related_bounties = ContextDisplayName('Bounties for %s')

root_index = 'The Launchpad Home Page'

rosetta_about = 'About Rosetta'

rosetta_index = 'Rosetta'

rosetta_preferences = 'Rosetta: Preferences'

product_branch_add = ContextDisplayName('Register a new branch for %s')

def productseries_edit(context, view):
    return 'Edit %s %s Details' % (context.product.displayname, context.name)

productseries_new = ContextDisplayName('Register a new %s release series')

def productseries(context, view):
    return '%s Release Series: %s' % (
        context.product.displayname, context.displayname)

shipit_index = 'ShipIt'

shipit_exports = 'ShipIt Exports'

shipit_myrequest = "Your ShipIt Order"

shipit_reports = 'ShipIt Reports'

shipitrequests_index = 'ShipIt Requests'

shipitrequests_search = 'Search ShipIt Requests'

shipitrequest_edit = 'Edit ShipIt Request'

shipit_notfound = 'Page Not Found'

shipit_default_error = 'System Error'

signedcodeofconduct_index = ContextDisplayName('%s')

signedcodeofconduct_add = ContextTitle('Sign %s')

signedcodeofconduct_acknowledge = 'Acknowledge Code of Conduct Signature'

signedcodeofconduct_activate = ContextDisplayName('Activating %s')

signedcodeofconduct_deactivate = ContextDisplayName('Deactivating %s')

sourcepackage = ContextTitle('%s')

sourcepackage_bugs = ContextDisplayName('Bugs in %s')

sourcepackage_buildlog = ContextTitle('%s Build Logs')

sourcepackage_builds = ContextTitle('%s Builds')

sourcepackage_translate = ContextTitle('Help translate %s')

sourcepackage_changelog = 'Source Package Changelog'

sourcepackage_filebug = ContextTitle("Report a bug about %s")

sourcepackage_gethelp = ContextTitle('Help and support options for %s')

sourcepackage_hctstatus = ContextTitle('Source Package HCT Status - %s')

def sourcepackage_index(context, view):
    return '%s Source Packages' % context.distrorelease.title

sourcepackage_packaging = ContextTitle('Define the Upstream Series of %s')

sourcepackage_translate = ContextTitle('Help translate %s')

sourcepackage_translations = ContextTitle(
    'Rosetta Translation Templates for %s')

sourcepackagebuild_buildlog = 'Source Package Build Log'

sourcepackagebuild_changes = 'Source Package Changes'

def sourcepackagebuild_index(context, view):
    return 'Builds: %s' % context.sourcepackagerelease.sourcepackage.summary

sourcepackagenames_index = 'Source package name set'

sourcepackagerelease_index = ContextTitle('Source Package %s')

def sourcepackages(context, view):
    return '%s Source Packages' % context.distrorelease.title

sourcepackages_comingsoon = 'Coming soon'

sources_index = 'Bazaar: Upstream Revision Control Imports'

sourcesource_index = 'Upstream Source Import'

specification_add = 'Register a feature specification in Launchpad'

specification_addsubscriber = 'Subscribe someone else to this spec'

specification_bug = ContextTitle(
  'Link specification \N{left double quotation mark}%s'
  '\N{right double quotation mark} to a bug report')

specification_removebug = 'Remove link to bug report'

specification_retargeting = 'Attach spec to a different product or distribution'

specification_superseding = 'Mark specification as superseded by another'

specification_dependency = 'Create a Specification Dependency'

specification_deptree = 'Complete Dependency Tree'

specification_milestone = 'Target Feature to Milestone'

specification_people = 'Change the Specification Assignee, Drafter and Reviewer'

specification_priority = 'Change the Specification Priority'

specification_distrorelease = ('Target Feature Specification at '
                               'Distribution Release')

specification_productseries = 'Target Feature Specification at Series'

specification_removedep = 'Remove a Dependency'

specification_givefeedback = 'Clear Feedback Requests'

specification_requestfeedback = 'Request Feedback on This Specification'

specification_edit = 'Edit Specification Details'

specification_linksprint = 'Put Specification on Sprint Agenda'

specification_status = 'Edit Specification Status'

specification_index = ContextTitle('Feature Specification: %s')

specification_subscription = 'Subscribe to Feature Specification'

specification_queue = 'Queue Feature Specification for Review'

specifications_index = ContextTitle('%s')

specificationtarget_specs = ContextTitle('Specifications for %s')

specificationtarget_specplan = ContextTitle('Project Plan for %s')

specificationtarget_workload = ContextTitle('Feature work load in %s')

sprint_attend = ContextTitle('Register your Attendance at %s')

sprint_edit = ContextTitle('Edit Meeting Details: %s')

sprint_index = ContextTitle('%s (Sprint or Meeting)')

sprint_new = 'Register a new Meeting or Sprint in Launchpad'

sprint_register = 'Register someone to attend this meeting'

sprint_table = ContextTitle('Table of Specs for %s')

sprint_workload = ContextTitle('Workload at %s')

sprints_index = 'Launchpad Meeting or Sprint Registry'

sprintspecification_edit = 'Edit details of spec at sprint.'

sprintspecification_admin = 'Approve spec for sprint agenda.'

tickets_index = 'Launchpad tech support system'

ticket_add = ContextDisplayName('Request support with %s')

ticket_bug = ContextId(u'Link support request #%s to a bug report')

ticket_edit = ContextId('Edit support request #%s details')

def ticket_index(context, view):
    text = (
        u'%s support request #%d: '
        u'\N{left double quotation mark}%s\N{right double quotation mark}'
        % (context.target.displayname, context.id, context.title))
    return text

ticket_history = ContextId('History of support request #%s')

ticket_makebug = ContextId('Create bug report based on request #%s')

ticket_reject = ContextId('Reject support request #%s')

ticket_removebug = ContextId('Remove bug link from request #%s')

ticket_reopen = ContextId('Reopen request #%s')

ticket_subscription = ContextId('Subscription to request #%s')

tickettarget_tickets = ContextTitle('Support requests for %s')

standardshipitrequests_index = 'Standard ShipIt Options'

standardshipitrequest_new = 'Create a New Standard Option'

standardshipitrequest_edit = 'Edit Standard Option'

team_addmember = ContextBrowsername('%s: Add Member')

team_edit = 'Edit Team Information'

team_editemail = ContextDisplayName('Edit %s Contact Email Address')

team_editproposed = ContextBrowsername('%s Proposed Members')

team_index = ContextBrowsername('"%s" team in Launchpad')

team_join = ContextBrowsername('Join %s')

team_leave = ContextBrowsername('Leave %s')

team_members = ContextBrowsername('%s members')

def teammembership_index(context, view):
    return 'Membership status for %s in %s' % (
        context.person.browsername, context.team.browsername)

team_newpoll = ContextTitle('Create a new Poll in team %s')

team_polls = ContextTitle('Polls in team %s')

template_auto_add = 'Launchpad Auto-Add Form'

template_auto_edit = 'Launchpad Auto-Edit Form'

template_edit = 'EXAMPLE EDIT TITLE'

template_index = '%EXAMPLE TITLE'

template_new = 'EXAMPLE NEW TITLE'

translationgroup = ContextTitle('Rosetta Translation Group: %s')
translationgroups = 'Rosetta Translation Groups'

translationimportqueueentry_index = 'Translation Import Queue Entry'
translationimportqueue_index = 'Translation Import Queue'
translationimportqueue_blocked = 'Translation Import Queue - Blocked'

# ul_main_template is probably obselete

unauthorized = 'Launchpad Permissions Notice'

user_error = 'Launchpad Error'

