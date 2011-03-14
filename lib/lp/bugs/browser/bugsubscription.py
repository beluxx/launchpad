# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Views for BugSubscription."""

__metaclass__ = type
__all__ = [
    'AdvancedSubscriptionMixin',
    'BugPortletDuplicateSubcribersContents',
    'BugPortletSubcribersContents',
    'BugSubscriptionAddView',
    'BugSubscriptionListView',
    ]

import cgi

from lazr.delegates import delegates
from simplejson import dumps
from zope import formlib
from zope.app.form import CustomWidgetFactory
from zope.app.form.browser.itemswidgets import RadioWidget
from zope.schema import Choice
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )

from canonical.launchpad import _
from canonical.launchpad.webapp import (
    canonical_url,
    LaunchpadView,
    )
from canonical.launchpad.webapp.authorization import check_permission
from canonical.launchpad.webapp.launchpadform import ReturnToReferrerMixin
from canonical.launchpad.webapp.menu import structured
from lp.app.browser.launchpadform import (
    action,
    LaunchpadFormView,
    )
from lp.bugs.browser.bug import BugViewMixin
from lp.bugs.enum import BugNotificationLevel, HIDDEN_BUG_NOTIFICATION_LEVELS
from lp.bugs.interfaces.bugsubscription import IBugSubscription
from lp.bugs.model.personsubscriptioninfo import PersonSubscriptions
from lp.services import features
from lp.services.propertycache import cachedproperty


class BugSubscriptionAddView(LaunchpadFormView):
    """Browser view class for subscribing someone else to a bug."""

    schema = IBugSubscription

    field_names = ['person']

    def setUpFields(self):
        """Set up 'person' as an input field."""
        super(BugSubscriptionAddView, self).setUpFields()
        self.form_fields['person'].for_input = True

    @action('Subscribe user', name='add')
    def add_action(self, action, data):
        person = data['person']
        self.context.bug.subscribe(person, self.user, suppress_notify=False)
        if person.isTeam():
            message = '%s team has been subscribed to this bug.'
        else:
            message = '%s has been subscribed to this bug.'
        self.request.response.addInfoNotification(
            message % person.displayname)

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url

    @property
    def label(self):
        return 'Subscribe someone else to bug #%i' % self.context.bug.id

    page_title = label


class AdvancedSubscriptionMixin:
    """A mixin of advanced subscription code for views.

    In order to use this mixin in a view the view must:
     - Define a current_user_subscription property which returns the
       current BugSubscription or StructuralSubscription for request.user.
       If there's no subscription for the given user in the given
       context, current_user_subscription must return None.
     - Define a dict, _bug_notification_level_descriptions, which maps
       BugNotificationLevel values to string descriptions for the
       current context (see `BugSubscriptionSubscribeSelfView` for an
       example).
     - Update the view's setUpFields() to call
       _setUpBugNotificationLevelField().
    """

    @cachedproperty
    def _use_advanced_features(self):
        """Return True if advanced subscriptions features are enabled."""
        return features.getFeatureFlag(
            'malone.advanced-subscriptions.enabled')

    @cachedproperty
    def _bug_notification_level_field(self):
        """Return a custom form field for bug_notification_level."""
        # We rebuild the items that we show in the field so that the
        # labels shown are human readable and specific to the +subscribe
        # form. The BugNotificationLevel descriptions are too generic.
        bug_notification_level_terms = [
            SimpleTerm(
                level, level.title,
                self._bug_notification_level_descriptions[level])
            # We reorder the items so that COMMENTS comes first. We also
            # drop the NOTHING option since it just makes the UI
            # confusing.
            for level in sorted(BugNotificationLevel.items, reverse=True)
                if level not in HIDDEN_BUG_NOTIFICATION_LEVELS]
        bug_notification_vocabulary = SimpleVocabulary(
            bug_notification_level_terms)

        if (self.current_user_subscription is not None and
            self.current_user_subscription.bug_notification_level not in
                HIDDEN_BUG_NOTIFICATION_LEVELS):
            default_value = (
                self.current_user_subscription.bug_notification_level)
        else:
            default_value = BugNotificationLevel.COMMENTS

        bug_notification_level_field = Choice(
            __name__='bug_notification_level', title=_("Tell me when"),
            vocabulary=bug_notification_vocabulary, required=True,
            default=default_value)
        return bug_notification_level_field

    def _setUpBugNotificationLevelField(self):
        """Set up the bug_notification_level field."""
        if not self._use_advanced_features:
            # If advanced features are disabled, do nothing.
            return

        self.form_fields = self.form_fields.omit('bug_notification_level')
        self.form_fields += formlib.form.Fields(
            self._bug_notification_level_field)
        self.form_fields['bug_notification_level'].custom_widget = (
            CustomWidgetFactory(RadioWidget))


class BugSubscriptionSubscribeSelfView(LaunchpadFormView,
                                       ReturnToReferrerMixin,
                                       AdvancedSubscriptionMixin):
    """A view to handle the +subscribe page for a bug."""

    schema = IBugSubscription

    # A mapping of BugNotificationLevel values to descriptions to be
    # shown on the +subscribe page.
    _bug_notification_level_descriptions = {
        BugNotificationLevel.LIFECYCLE: (
            "The bug is fixed or re-opened."),
        BugNotificationLevel.METADATA: (
            "Any change is made to this bug, other than a new comment "
            "being added."),
        BugNotificationLevel.COMMENTS: (
            "A change is made to this bug or a new comment is added."),
        }

    @property
    def field_names(self):
        if self._use_advanced_features:
            return ['bug_notification_level']
        else:
            return []

    @property
    def next_url(self):
        """Provided so returning to the page they came from works."""
        referer = self._return_url
        context_url = canonical_url(self.context)

        # XXX bdmurray 2010-09-30 bug=98437: work around zope's test
        # browser setting referer to localhost.
        # We also ignore the current request URL and the context URL as
        # far as referrers are concerned so that we can handle privacy
        # issues properly.
        ignored_referrer_urls = (
            'localhost', self.request.getURL(), context_url)
        if referer and referer not in ignored_referrer_urls:
            next_url = referer
        elif self._redirecting_to_bug_list:
            next_url = canonical_url(self.context.target, view_name="+bugs")
        else:
            next_url = context_url
        return next_url

    cancel_url = next_url

    @cachedproperty
    def _subscribers_for_current_user(self):
        """Return a dict of the subscribers for the current user."""
        persons_for_user = {}
        person_count = 0
        bug = self.context.bug
        for person in bug.getSubscribersForPerson(self.user):
            if person.id not in persons_for_user:
                persons_for_user[person.id] = person
                person_count += 1

        self._subscriber_count_for_current_user = person_count
        return persons_for_user.values()

    def initialize(self):
        """See `LaunchpadFormView`."""
        self._subscriber_count_for_current_user = 0
        self._redirecting_to_bug_list = False
        super(BugSubscriptionSubscribeSelfView, self).initialize()

    @cachedproperty
    def current_user_subscription(self):
        return self.context.bug.getSubscriptionForPerson(self.user)

    @cachedproperty
    def _update_subscription_term(self):
        return SimpleTerm(
            'update-subscription', 'update-subscription',
            'Update my current subscription')

    @cachedproperty
    def _subscription_field(self):
        subscription_terms = []
        self_subscribed = False
        for person in self._subscribers_for_current_user:
            if person.id == self.user.id:
                if (self._use_advanced_features and
                    self.user_is_subscribed_directly):
                    subscription_terms.append(self._update_subscription_term)
                subscription_terms.insert(
                    0, SimpleTerm(
                        person, person.name,
                        'Unsubscribe me from this bug'))
                self_subscribed = True
            else:
                subscription_terms.append(
                    SimpleTerm(
                        person, person.name,
                        'Unsubscribe <a href="%s">%s</a> from this bug' % (
                            canonical_url(person),
                            cgi.escape(person.displayname))))
        if not self_subscribed:
            subscription_terms.insert(0,
                SimpleTerm(
                    self.user, self.user.name, 'Subscribe me to this bug'))
        subscription_vocabulary = SimpleVocabulary(subscription_terms)
        if (self._use_advanced_features and
            self.user_is_subscribed_directly):
            default_subscription_value = self._update_subscription_term.value
        else:
            default_subscription_value = (
                subscription_vocabulary.getTermByToken(self.user.name).value)
        subscription_field = Choice(
            __name__='subscription', title=_("Subscription options"),
            vocabulary=subscription_vocabulary, required=True,
            default=default_subscription_value)
        return subscription_field

    def setUpFields(self):
        """See `LaunchpadFormView`."""
        super(BugSubscriptionSubscribeSelfView, self).setUpFields()
        if self.user is None:
            return

        self.form_fields += formlib.form.Fields(self._subscription_field)
        self._setUpBugNotificationLevelField()
        self.form_fields['subscription'].custom_widget = CustomWidgetFactory(
            RadioWidget)

    def setUpWidgets(self):
        """See `LaunchpadFormView`."""
        super(BugSubscriptionSubscribeSelfView, self).setUpWidgets()
        if self._use_advanced_features:
            if self._subscriber_count_for_current_user == 0:
                # We hide the subscription widget if the user isn't
                # subscribed, since we know who the subscriber is and we
                # don't need to present them with a single radio button.
                self.widgets['subscription'].visible = False
            else:
                # We show the subscription widget when the user is
                # subscribed via a team, because they can either
                # subscribe theirself or unsubscribe their team.
                self.widgets['subscription'].visible = True

            if (self.user_is_subscribed and
                self.user_is_subscribed_to_dupes_only):
                # If the user is subscribed via a duplicate but is not
                # directly subscribed, we hide the
                # bug_notification_level field, since it's not used.
                self.widgets['bug_notification_level'].visible = False

    @cachedproperty
    def user_is_subscribed_directly(self):
        """Is the user subscribed directly to this bug?"""
        return self.context.bug.isSubscribed(self.user)

    @cachedproperty
    def user_is_subscribed_to_dupes(self):
        """Is the user subscribed to dupes of this bug?"""
        return self.context.bug.isSubscribedToDupes(self.user)

    @property
    def user_is_subscribed(self):
        """Is the user subscribed to this bug?"""
        return (
            self.user_is_subscribed_directly or
            self.user_is_subscribed_to_dupes)

    @property
    def user_is_subscribed_to_dupes_only(self):
        """Is the user subscribed to this bug only via a dupe?"""
        return (
            self.user_is_subscribed_to_dupes and
            not self.user_is_subscribed_directly)

    def shouldShowUnsubscribeFromDupesWarning(self):
        """Should we warn the user about unsubscribing and duplicates?

        The warning should tell the user that, when unsubscribing, they
        will also be unsubscribed from dupes of this bug.
        """
        if self.user_is_subscribed:
            return True

        bug = self.context.bug
        for team in self.user.teams_participated_in:
            if bug.isSubscribed(team) or bug.isSubscribedToDupes(team):
                return True

        return False

    @action('Continue', name='continue')
    def subscribe_action(self, action, data):
        """Handle subscription requests."""
        subscription_person = self.widgets['subscription'].getInputValue()
        if self._use_advanced_features:
            bug_notification_level = data.get('bug_notification_level', None)
        else:
            bug_notification_level = None

        if (subscription_person == self._update_subscription_term.value and
            self.user_is_subscribed):
            self._handleUpdateSubscription(level=bug_notification_level)
        elif (not self.user_is_subscribed and
            (subscription_person == self.user)):
            self._handleSubscribe(bug_notification_level)
        else:
            self._handleUnsubscribe(subscription_person)
        self.request.response.redirect(self.next_url)

    def _handleSubscribe(self, level=None):
        """Handle a subscribe request."""
        self.context.bug.subscribe(self.user, self.user, level=level)
        self.request.response.addNotification(
            "You have been subscribed to this bug.")

    def _handleUnsubscribe(self, user):
        """Handle an unsubscribe request."""
        if user == self.user:
            self._handleUnsubscribeCurrentUser()
        else:
            self._handleUnsubscribeOtherUser(user)

    def _handleUnsubscribeCurrentUser(self):
        """Handle the special cases for unsubscribing the current user.

        when the bug is private. The user must be unsubscribed from all dupes
        too, or they would keep getting mail about this bug!
        """
        # ** Important ** We call unsubscribeFromDupes() before
        # unsubscribe(), because if the bug is private, the current user
        # will be prevented from calling methods on the main bug after
        # they unsubscribe from it!
        unsubed_dupes = self.context.bug.unsubscribeFromDupes(
            self.user, self.user)
        self.context.bug.unsubscribe(self.user, self.user)

        self.request.response.addNotification(
            structured(
                self._getUnsubscribeNotification(self.user, unsubed_dupes)))

        # Because the unsubscribe above may change what the security policy
        # says about the bug, we need to clear its cache.
        self.request.clearSecurityPolicyCache()

        if not check_permission("launchpad.View", self.context.bug):
            # Redirect the user to the bug listing, because they can no
            # longer see a private bug from which they've unsubscribed.
            self._redirecting_to_bug_list = True

    def _handleUnsubscribeOtherUser(self, user):
        """Handle unsubscribing someone other than the current user."""
        assert user != self.user, (
            "Expected a user other than the currently logged-in user.")

        # We'll also unsubscribe the other user from dupes of this bug,
        # otherwise they'll keep getting this bug's mail.
        self.context.bug.unsubscribe(user, self.user)
        unsubed_dupes = self.context.bug.unsubscribeFromDupes(user, user)
        self.request.response.addNotification(
            structured(
                self._getUnsubscribeNotification(user, unsubed_dupes)))

    def _handleUpdateSubscription(self, level):
        """Handle updating a user's subscription."""
        subscription = self.current_user_subscription
        subscription.bug_notification_level = level
        self.request.response.addNotification(
            "Your subscription to this bug has been updated.")

    def _getUnsubscribeNotification(self, user, unsubed_dupes):
        """Construct and return the unsubscribe-from-bug feedback message.

        :user: The IPerson or ITeam that was unsubscribed from the bug.
        :unsubed_dupes: The list of IBugs that are dupes from which the
                        user was unsubscribed.
        """
        current_bug = self.context.bug
        current_user = self.user
        unsubed_dupes_msg_fragment = self._getUnsubscribedDupesMsgFragment(
            unsubed_dupes)

        if user == current_user:
            # Consider that the current user may have been "locked out"
            # of a bug if they unsubscribed themselves from a private
            # bug!
            if check_permission("launchpad.View", current_bug):
                # The user still has permission to see this bug, so no
                # special-casing needed.
                return (
                    "You have been unsubscribed from bug %d%s." % (
                    current_bug.id, unsubed_dupes_msg_fragment))
            else:
                return (
                    "You have been unsubscribed from bug %d%s. You no "
                    "longer have access to this private bug.") % (
                        current_bug.id, unsubed_dupes_msg_fragment)
        else:
            return "%s has been unsubscribed from bug %d%s." % (
                cgi.escape(user.displayname), current_bug.id,
                unsubed_dupes_msg_fragment)

    def _getUnsubscribedDupesMsgFragment(self, unsubed_dupes):
        """Return the duplicates fragment of the unsubscription notification.

        This piece lists the duplicates from which the user was
        unsubscribed.
        """
        if not unsubed_dupes:
            return ""

        dupe_links = []
        for unsubed_dupe in unsubed_dupes:
            dupe_links.append(
                '<a href="%s" title="%s">#%d</a>' % (
                canonical_url(unsubed_dupe), unsubed_dupe.title,
                unsubed_dupe.id))
        dupe_links_string = ", ".join(dupe_links)

        num_dupes = len(unsubed_dupes)
        if num_dupes > 1:
            plural_suffix = "s"
        else:
            plural_suffix = ""

        return (
            " and %(num_dupes)d duplicate%(plural_suffix)s "
            "(%(dupe_links_string)s)") % ({
                'num_dupes': num_dupes,
                'plural_suffix': plural_suffix,
                'dupe_links_string': dupe_links_string})


class BugPortletSubcribersContents(LaunchpadView, BugViewMixin):
    """View for the contents for the subscribers portlet."""

    @property
    def sorted_direct_subscriptions(self):
        """Get the list of direct subscriptions to the bug.

        The list is sorted such that subscriptions you can unsubscribe appear
        before all other subscriptions.
        """
        direct_subscriptions = [
            SubscriptionAttrDecorator(subscription)
            for subscription in self.context.getDirectSubscriptions().sorted]
        can_unsubscribe = []
        cannot_unsubscribe = []
        for subscription in direct_subscriptions:
            if not check_permission('launchpad.View', subscription.person):
                continue
            if subscription.person == self.user:
                can_unsubscribe = [subscription] + can_unsubscribe
            elif subscription.canBeUnsubscribedByUser(self.user):
                can_unsubscribe.append(subscription)
            else:
                cannot_unsubscribe.append(subscription)
        return can_unsubscribe + cannot_unsubscribe


class BugPortletDuplicateSubcribersContents(LaunchpadView, BugViewMixin):
    """View for the contents for the subscribers-from-dupes portlet block."""

    @property
    def sorted_subscriptions_from_dupes(self):
        """Get the list of subscriptions to duplicates of this bug."""
        return [
            SubscriptionAttrDecorator(subscription)
            for subscription in sorted(
                self.context.getSubscriptionsFromDuplicates(),
                key=(lambda subscription: subscription.person.displayname))]


class BugPortletSubcribersIds(LaunchpadView, BugViewMixin):
    """A view that returns a JSON dump of the subscriber IDs for a bug."""

    @property
    def subscriber_ids_js(self):
        """Return subscriber_ids in a form suitable for JavaScript use."""
        return dumps(self.subscriber_ids)

    def render(self):
        """Override the default render() to return only JSON."""
        self.request.response.setHeader('content-type', 'application/json')
        return self.subscriber_ids_js


class SubscriptionAttrDecorator:
    """A BugSubscription with added attributes for HTML/JS."""
    delegates(IBugSubscription, 'subscription')

    def __init__(self, subscription):
        self.subscription = subscription

    @property
    def css_name(self):
        return 'subscriber-%s' % self.subscription.person.id

# These are the descriptions strings of what might be the cause of you getting
# an email.

_BECAUSE_YOU_ARE = 'You receive emails about this bug because you are '
# These are components for team participation.
_OF_TEAM = 'of the team $(team)s. That team is '
_OF_TEAMS = 'of the teams $(teams)s.  Those teams are '
_BECAUSE_TEAM_IS = _BECAUSE_YOU_ARE + 'a member ' + _OF_TEAM
_ADMIN_BECAUSE_TEAM_IS = (
    _BECAUSE_YOU_ARE + 'a member and administrator ' + _OF_TEAM)
_BECAUSE_TEAMS_ARE = _BECAUSE_YOU_ARE + 'a member ' + _OF_TEAMS
_ADMIN_BECAUSE_TEAMS_ARE = (
    _BECAUSE_YOU_ARE + 'a member and administrator ' + _OF_TEAMS)
    
# These are the assignment variations.
# These are components.
_ASSIGNED = 'assigned to work on it.'
# These are the actual strings to use.
YOU_ASSIGNED = _BECAUSE_YOU_ARE + _ASSIGNED
TEAM_ASSIGNED = _BECAUSE_TEAM_IS + _ASSIGNED
ADMIN_TEAM_ASSIGNED = _ADMIN_BECAUSE_TEAM_IS + _ASSIGNED
TEAMS_ASSIGNED = _BECAUSE_TEAMS_ARE + _ASSIGNED
ADMIN_TEAMS_ASSIGNED = _ADMIN_BECAUSE_TEAMS_ARE + _ASSIGNED

# These are the direct subscription variations.
# First we have the string components.
_SUBSCRIBED = 'directly subscribed to it.'
_MAY_HAVE_BEEN_CREATED = ' This subscription may have been created '
# Now these are the actual options we use.
YOU_SUBSCRIBED = _BECAUSE_YOU_ARE + _SUBSCRIBED
YOU_REPORTED = (YOU_SUBSCRIBED + _MAY_HAVE_BEEN_CREATED +
                'when you reported the bug.')
YOU_SUBSCRIBED_BUG_SUPERVISOR = (
    YOU_SUBSCRIBED + _MAY_HAVE_BEEN_CREATED +
    'because the bug was private and you are a bug supervisor.')
YOU_SUBSCRIBED_SECURITY_CONTACT = (
    YOU_SUBSCRIBED + _MAY_HAVE_BEEN_CREATED +
    'because the bug was security related and you are a security contact.')
TEAM_SUBSCRIBED = _BECAUSE_TEAM_IS + _SUBSCRIBED
ADMIN_TEAM_SUBSCRIBED = _ADMIN_BECAUSE_TEAM_IS + _SUBSCRIBED
TEAMS_SUBSCRIBED = _BECAUSE_TEAMS_ARE + _SUBSCRIBED
ADMIN_TEAMS_SUBSCRIBED = _ADMIN_BECAUSE_TEAMS_ARE + _SUBSCRIBED

# These are the duplicate bug variations.
_SUBSCRIBED_TO_DUPLICATE = (
    'a direct subscriber to bug #$(dupe_bug_id)s, which is marked as a '
    'duplicate of this bug, #$(bug_id)s')
_SUBSCRIBED_TO_PRIMARY = (
    'a direct subscriber to bug #$(primary_bug_id)s, of which this bug, '
    '#$(bug_id)s, is marked a duplicate.')
# These are the actual strings to use.
YOU_SUBSCRIBED_TO_DUPLICATE = _BECAUSE_YOU_ARE + _SUBSCRIBED_TO_DUPLICATE
YOU_SUBSCRIBED_TO_PRIMARY = _BECAUSE_YOU_ARE + _SUBSCRIBED_TO_PRIMARY
TEAM_SUBSCRIBED_TO_DUPLICATE = _BECAUSE_TEAM_IS + _SUBSCRIBED_TO_DUPLICATE
ADMIN_TEAM_SUBSCRIBED_TO_DUPLICATE = (
    _ADMIN_BECAUSE_TEAM_IS + _SUBSCRIBED_TO_DUPLICATE)
TEAMS_SUBSCRIBED_TO_DUPLICATE = _BECAUSE_TEAMS_ARE + _SUBSCRIBED_TO_DUPLICATE
ADMIN_TEAMS_SUBSCRIBED_TO_DUPLICATE = (
    _ADMIN_BECAUSE_TEAMS_ARE + _SUBSCRIBED_TO_DUPLICATE)
TEAM_SUBSCRIBED_TO_PRIMARY = _BECAUSE_TEAM_IS + _SUBSCRIBED_TO_PRIMARY
ADMIN_TEAM_SUBSCRIBED_TO_PRIMARY = (
    _ADMIN_BECAUSE_TEAM_IS + _SUBSCRIBED_TO_PRIMARY)
TEAMS_SUBSCRIBED_TO_PRIMARY = _BECAUSE_TEAMS_ARE + _SUBSCRIBED_TO_PRIMARY
ADMIN_TEAMS_SUBSCRIBED_TO_PRIMARY = (
    _ADMIN_BECAUSE_TEAMS_ARE + _SUBSCRIBED_TO_PRIMARY)

# These are the owner variations.
_OWNER = ("the owner of the $(pillar_type) "
          "<a href='$(pillar_url)'>$(pillar_name)</a>, which has no bug "
          "supervisor."
YOU_OWNER = _BECAUSE_YOU_ARE + _OWNER
TEAM_OWNER = _BECAUSE_TEAM_IS + _OWNER
ADMIN_TEAM_OWNER = _ADMIN_BECAUSE_TEAM_IS + _OWNER
TEAMS_OWNER = _BECAUSE_TEAMS_ARE + _OWNER

# That's 27 options.
# Also: "You are not subscribed to this bug." or similar.
# Also: "You have muted all email from this bug."

# Actions for a person
# "Control the email you receive about bug #XXXX"
MUTE_ACTION = ( # Always present.
    ('title', "Mute all email from bug #$(bug_id)s"),
    ('description', "You will receive no further email about the bug."))
CHANGE_SUBSCRIPTION_ACTION = ( # If you are subscribed directly.
    ('title', 'Change your subscription to bug #$(bug_id)s'),
    ('description', 'Change which events will trigger an email.'))
UNSUBSCRIBE_ACTION = ( # If you are subscribed directly.
    # WARNING: IF THIS IS A PRIVATE BUG, YOU ARE TAKING AWAY THE PRIVILEGES
    # TO SEE THE BUG. XXX
    ('title', 'Unsubscribe from bug #$(bug_id)s'),
    ('description', "You will no longer receive email about this bug."))
REPORTER_UNSUBSCRIBE_ACTION = ( # If you are subscribed directly and reporter.
    # WARNING: IF THIS IS A PRIVATE BUG, YOU ARE TAKING AWAY THE PRIVILEGES
    # TO SEE THE BUG. XXX
    ('title', 'Unsubscribe from bug #$(bug_id)s'),
    ('description', "You will no longer receive email about this bug. It "
                    "will still show in the list of bugs you've reported."))
MUTE_COMMENTS_ACTION = ( # If you are not subscribed directly
    ('title', 'Mute emails from bug #$(bug_id)s that only contain comments.'),
    ('description', 'Add a direct subscription to the bug that limits the '
                    'emails you receive about it.'))
MUTE_ALL_BUT_CLOSE_ACTION = ( # If you are not subscribed directly
    ('title': 'Mute all emails from bug #$(bug_id)s except when it closes.'),
    ('description', 'Add a direct subscription to the bug that limits the '
                    'emails you receive about it.'))
"""


  * Unsubscribe from duplicate — subscribed from duplicate

    * ACTION: Unsubscribe from bug #XXXX

    * DESCRIPTION: You subscribed to a bug that was later marked as a duplicate of another bug. You will receive no further email about this bug but you'll still receive email about the other bug.

GROUP "Control the email you and others receive about bug #XXXX"

  * Unsubscribe team from the bug — indirectly through team as team admin

    * ACTION: Unsubscribe $TEAM from bug #XXX

    * DESCRIPTION: This team will no longer receive email about this bug. This will not affect individual subscriptions made by team members.

  * Unsubscribe team from the duplicate — admin of a team subscribed to the duplicate

    * ACTION: Unsubscribe $TEAM from bug #XXXX

    * DESCRIPTION: You subscribed this team to a bug that was later marked as a duplicate of another bug. The team will receive no further email about this bug but will still receive email about the other bug.

  * Change team subscription level — indirectly through team as team admin

    * ACTION: Change $TEAM's subscription to bug #XXXX

    * DESCRIPTION: Change which events will trigger an email to this team.

  * Set the bug supervisor — no bug supervisor, you are the product owner

    * ACTION: Set $PROJECT's bug supervisor

    * DESCRIPTION: Choose an individual or team who will manage bug reports for this project.
"""

class BugSubscriptionListView(LaunchpadView):
    """A view to show all a person's subscriptions to a bug."""

    @property
    def label(self):
        return "Your subscriptions to bug %d" % self.context.bug.id

    page_title = label

    def initialize(self):
        super(BugSubscriptionListView, self).initialize()
        if self.user is not None:
            self.structural_subscriptions = (
                self.context.bug.getStructuralSubscriptionsForPerson(
                    self.user))
            self.subscriptions_info = PersonSubscriptions(
                self.user, self.context.bug)
            self.
        else:
            self.subscriptions_info = self.structural_subscriptions = None
