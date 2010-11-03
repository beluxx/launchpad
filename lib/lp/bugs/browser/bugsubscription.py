# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Views for BugSubscription."""

__metaclass__ = type
__all__ = [
    'BugPortletDuplicateSubcribersContents',
    'BugPortletSubcribersContents',
    'BugSubscriptionAddView',
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
    action,
    canonical_url,
    LaunchpadFormView,
    LaunchpadView,
    )
from canonical.launchpad.webapp.authorization import check_permission
from canonical.launchpad.webapp.launchpadform import ReturnToReferrerMixin
from canonical.launchpad.webapp.menu import structured
from lp.bugs.browser.bug import BugViewMixin
from lp.bugs.interfaces.bugsubscription import IBugSubscription
from lp.registry.enum import BugNotificationLevel
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


class BugSubscriptionSubscribeSelfView(LaunchpadFormView,
                                       ReturnToReferrerMixin):
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

    @cachedproperty
    def _use_advanced_features(self):
        """Return True if advanced subscriptions features are enabled."""
        return features.getFeatureFlag(
            'malone.advanced-subscriptions.enabled')

    def initialize(self):
        """See `LaunchpadFormView`."""
        self._subscriber_count_for_current_user = 0
        self._redirecting_to_bug_list = False
        super(BugSubscriptionSubscribeSelfView, self).initialize()

    @cachedproperty
    def _bug_notification_level_field(self):
        """Return a custom form field for bug_notification_level."""
        # We rebuild the items that we show in the field so that the
        # labels shown are human readable and specific to the +subscribe
        # form. The BugNotificationLevel descriptions are too generic.
        bug_notification_level_terms = [
            SimpleTerm(
                level, level.name,
                self._bug_notification_level_descriptions[level])
            # We reorder the items so that COMMENTS comes first. We also
            # drop the NOTHING option since it just makes the UI
            # confusing.
            for level in sorted(BugNotificationLevel.items, reverse=True)
                if level != BugNotificationLevel.NOTHING
            ]
        bug_notification_vocabulary = SimpleVocabulary(
            bug_notification_level_terms)
        bug_notification_level_field = Choice(
            __name__='bug_notification_level', title=_("Tell me when"),
            vocabulary=bug_notification_vocabulary, required=True,
            default=BugNotificationLevel.COMMENTS)
        return bug_notification_level_field

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
                if self._use_advanced_features:
                    subscription_terms.append(self._update_subscription_term)
                subscription_terms.append(
                    SimpleTerm(
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
        if self.user_is_subscribed and self._use_advanced_features:
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

        if self._use_advanced_features:
            self.form_fields = self.form_fields.omit('bug_notification_level')
            self.form_fields += formlib.form.Fields(self._subscription_field)
            self.form_fields += formlib.form.Fields(
                self._bug_notification_level_field)
            self.form_fields['bug_notification_level'].custom_widget = (
                CustomWidgetFactory(RadioWidget))
        else:
            self.form_fields += formlib.form.Fields(self._subscription_field)
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

    @cachedproperty
    def user_is_subscribed(self):
        """Is the user subscribed to this bug?"""
        return (
            self.context.bug.isSubscribed(self.user) or
            self.context.bug.isSubscribedToDupes(self.user))

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
            bug_notification_level = data['bug_notification_level']
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
        bug = self.context.bug
        subscription = bug.getSubscriptionForPerson(self.user)
        subscription.bug_notification_level = level

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
            for subscription in self.context.getDirectSubscriptions()]
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
                key=(lambda subscription: subscription.person.displayname))
            ]


class BugPortletSubcribersIds(LaunchpadView, BugViewMixin):
    """A view that returns a JSON dump of the subscriber IDs for a bug."""

    @property
    def subscriber_ids_js(self):
        """Return subscriber_ids in a form suitable for JavaScript use."""
        return dumps(self.subscriber_ids)

    def render(self):
        """Override the default render() to return only JSON."""
        return self.subscriber_ids_js


class SubscriptionAttrDecorator:
    """A BugSubscription with added attributes for HTML/JS."""
    delegates(IBugSubscription, 'subscription')

    def __init__(self, subscription):
        self.subscription = subscription

    @property
    def css_name(self):
        return 'subscriber-%s' % self.subscription.person.id
