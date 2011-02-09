# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser view classes related to bug nominations."""

__metaclass__ = type

__all__ = [
    'BugNominationContextMenu',
    'BugNominationView',
    'BugNominationEditView',
    'BugNominationTableRowView']

import datetime

import pytz
from zope.component import getUtility
from zope.publisher.interfaces import (
    implements,
    NotFound,
    )

from canonical.launchpad import _
from canonical.launchpad.webapp import (
    canonical_url,
    LaunchpadView,
    )
from canonical.launchpad.webapp.authorization import check_permission
from canonical.launchpad.webapp.interfaces import (
    ILaunchBag,
    IPrimaryContext,
    )
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadFormView,
    )
from lp.app.widgets.itemswidgets import LabeledMultiCheckBoxWidget
from lp.bugs.browser.bug import BugContextMenu
from lp.bugs.interfaces.bugnomination import (
    IBugNomination,
    IBugNominationForm,
    )
from lp.bugs.interfaces.bugtask import INullBugTask
from lp.bugs.interfaces.cve import ICveSet


class BugNominationPrimaryContext:
    """The primary context is the nearest `IBugTarget`."""
    implements(IPrimaryContext)

    def __init__(self, nomination):
        launchbag = getUtility(ILaunchBag)
        self.context = launchbag.bugtask.target


class BugNominationView(LaunchpadFormView):

    schema = IBugNominationForm
    initial_focus_widget = None
    custom_widget('nominatable_series', LabeledMultiCheckBoxWidget)

    def __init__(self, context, request):
        self.current_bugtask = context
        LaunchpadFormView.__init__(self, context, request)

    def initialize(self):
        if INullBugTask.providedBy(self.current_bugtask):
            # It shouldn't be possible to nominate a bug that hasn't
            # been reported yet.
            raise NotFound(self.current_bugtask, '+nominate', self.request)
        LaunchpadFormView.initialize(self)
        # Update the submit label based on the user's permission.
        submit_action = self.__class__.actions.byname['actions.submit']
        if self.userIsReleaseManager():
            submit_action.label = _("Target")
        else:
            submit_action.label = _("Nominate")

    @property
    def label(self):
        """Return a nomination or targeting label.

        The label returned depends on the user's privileges.
        """
        if self.userIsReleaseManager():
            return "Target bug #%d to series" % self.context.bug.id
        else:
            return "Nominate bug #%d for series" % self.context.bug.id

    page_title = label

    def userIsReleaseManager(self):
        """Does the current user have release management privileges?"""
        current_bugtask = getUtility(ILaunchBag).bugtask
        return check_permission(
            "launchpad.Driver", current_bugtask.target)

    def userCanChangeDriver(self):
        """Can the current user set the release management team?"""
        return check_permission(
            "launchpad.Edit", self.getReleaseContext())

    def getReleaseManager(self):
        """Return the IPerson or ITeam that does release management."""
        # XXX: Brad Bollenbach 2006-10-31:
        # Ignoring the "drivers" attribute for now, which includes the
        # project-wide driver for upstreams because I'm guessing it's
        # hardly used, and would make displaying release managers a
        # little harder.
        return self.getReleaseContext().driver

    def getReleaseContext(self):
        """Get the distribution or product for release management."""
        launchbag = getUtility(ILaunchBag)
        return launchbag.product or launchbag.distribution

    @action(_("Submit"), name="submit")
    def nominate(self, action, data):
        """Nominate bug for series."""
        nominatable_series = data["nominatable_series"]
        nominated_series = []
        approved_nominations = []

        for series in nominatable_series:
            nomination = self.context.bug.addNomination(
                target=series, owner=self.user)

            # If the user has the permission to approve the nomination,
            # we approve it automatically.
            if nomination.canApprove(self.user):
                nomination.approve(self.user)
                approved_nominations.append(
                    nomination.target.bugtargetdisplayname)
            else:
                nominated_series.append(series.bugtargetdisplayname)

        if approved_nominations:
            self.request.response.addNotification(
                "Targeted bug to: %s" %
                ", ".join(approved_nominations))
        if nominated_series:
            self.request.response.addNotification(
                "Added nominations for: %s" %
                ", ".join(nominated_series))

    @property
    def next_url(self):
        return canonical_url(getUtility(ILaunchBag).bugtask)


class BugNominationTableRowView(LaunchpadView):
    """Browser view class for rendering a nomination table row."""

    # This method will be called to render the bug nomination.
    renderNonConjoinedSlave = LaunchpadView.__call__

    def getNominationPerson(self):
        """Return the IPerson associated with this nomination.

        Return the "decider" (the person who approved or declined the
        nomination), if there is one, otherwise return the owner.
        """
        return self.context.decider or self.context.owner

    def getNominationEditLink(self):
        """Return a link to the nomination edit form."""
        return (
            "%s/nominations/%d/+editstatus" % (
                canonical_url(getUtility(ILaunchBag).bugtask),
                self.context.id))

    def getApproveDeclineLinkText(self):
        """Return a string used for the approve/decline form expander link."""
        if self.context.isProposed():
            return "approve/decline"
        elif self.context.isDeclined():
            return "approve"
        else:
            assert (
                "Expected nomination to be Proposed or Declined. "
                "Got status: %s" % self.context.status.title)

    def getNominationDurationSinceCreatedOrDecided(self):
        """Return a duration since this nomination was created or decided.

        So if the nomination is currently Proposed, the duration will be from
        date_created to now, and if the nomination is Approved/Declined, the
        duration will be from date_decided until now.

        This allows us to present a human-readable version of how long ago
        the nomination was created or approved/declined.
        """
        UTC = pytz.timezone('UTC')
        now = datetime.datetime.now(UTC)
        bugnomination = self.context

        if bugnomination.date_decided:
            return now - bugnomination.date_decided

        return now - bugnomination.date_created

    def userCanMakeDecisionForNomination(self):
        """Can the user approve/decline this nomination?"""
        return check_permission("launchpad.Driver", self.context)

    def displayNominationEditLinks(self):
        """Return true if the Nomination edit links should be shown."""
        # Hide the link when the bug is viewed in a CVE context
        return self.request.getNearest(ICveSet) == (None, None)


class BugNominationEditView(LaunchpadView):
    """Browser view class for approving and declining nominations."""

    def __init__(self, context, request):
        LaunchpadView.__init__(self, context, request)
        self.current_bugtask = getUtility(ILaunchBag).bugtask

    def getFormAction(self):
        """Get the string used as the form action."""
        return (
            "%s/nominations/%d/+edit-form" % (
                canonical_url(self.current_bugtask), self.context.id))

    def processNominationDecision(self):
        """Process the decision made on this nomination."""
        form = self.request.form
        approve_nomination = form.get("approve")
        decline_nomination = form.get("decline")

        if not (approve_nomination or decline_nomination):
            return

        if approve_nomination:
            self.context.approve(self.user)
            self.request.response.addNotification(
                "Approved nomination for %s" %
                    self.context.target.bugtargetdisplayname)
        elif decline_nomination:
            self.context.decline(self.user)
            self.request.response.addNotification(
                "Declined nomination for %s" %
                    self.context.target.bugtargetdisplayname)

        self.request.response.redirect(
            canonical_url(getUtility(ILaunchBag).bugtask))

    def shouldShowApproveButton(self):
        """Should the approve button be shown?"""
        return self.context.isProposed() or self.context.isDeclined()

    def shouldShowDeclineButton(self):
        """Should the decline button be shown?"""
        return self.context.isProposed()

    def getCurrentBugTaskURL(self):
        """Return the URL of the current bugtask."""
        return canonical_url(getUtility(ILaunchBag).bugtask)

    @property
    def title(self):
        return 'Approve or decline nomination for bug #%d in %s' % (
            self.context.bug.id, self.context.target.bugtargetdisplayname)


class BugNominationContextMenu(BugContextMenu):
    usedfor = IBugNomination
