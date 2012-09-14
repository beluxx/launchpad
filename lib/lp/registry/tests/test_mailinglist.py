# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = []

from textwrap import dedent
import transaction

from zope.component import getUtility

from lp.registry.interfaces.mailinglist import (
    CannotSubscribe,
    IHeldMessageDetails,
    IMailingListSet,
    IMessageApprovalSet,
    MailingListStatus,
    PostedMessageStatus,
    )
from lp.registry.interfaces.mailinglistsubscription import (
    MailingListAutoSubscribePolicy,
    )
from lp.registry.interfaces.person import TeamMembershipPolicy
from lp.services.messages.interfaces.message import IMessageSet
from lp.testing import (
    login_celebrity,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.mail_helpers import pop_notifications


class PersonMailingListTestCase(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_autoSubscribeToMailingList_ON_REGISTRATION_someone_else(self):
        # Users with autoSubscribeToMailingList set to ON_REGISTRATION
        # are not subscribed when someone else adds them.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        subscribed = member.autoSubscribeToMailingList(
            team.mailing_list, team.teamowner)
        self.assertEqual(
            MailingListAutoSubscribePolicy.ON_REGISTRATION,
            member.mailing_list_auto_subscribe_policy)
        self.assertIs(False, subscribed)
        self.assertEqual(None, team.mailing_list.getSubscription(member))

    def test_autoSubscribeToMailingList_ON_REGISTRATION_user(self):
        # Users with autoSubscribeToMailingList set to ON_REGISTRATION
        # are subscribed when when they add them selves.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        subscribed = member.autoSubscribeToMailingList(team.mailing_list)
        self.assertEqual(
            MailingListAutoSubscribePolicy.ON_REGISTRATION,
            member.mailing_list_auto_subscribe_policy)
        self.assertIs(True, subscribed)
        self.assertIsNot(None, team.mailing_list.getSubscription(member))

    def test_autoSubscribeToMailingList_ALWAYS(self):
        # When autoSubscribeToMailingList set to ALWAYS
        # users subscribed when when added by anyone.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        with person_logged_in(member):
            member.mailing_list_auto_subscribe_policy = (
                MailingListAutoSubscribePolicy.ALWAYS)
        subscribed = member.autoSubscribeToMailingList(
            team.mailing_list, team.teamowner)
        self.assertIs(True, subscribed)
        self.assertIsNot(None, team.mailing_list.getSubscription(member))

    def test_autoSubscribeToMailingList_NEVER(self):
        # When autoSubscribeToMailingList set to NEVER
        # users are never subscribed.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        with person_logged_in(member):
            member.mailing_list_auto_subscribe_policy = (
                MailingListAutoSubscribePolicy.NEVER)
        subscribed = member.autoSubscribeToMailingList(team.mailing_list)
        self.assertIs(False, subscribed)
        self.assertIs(None, team.mailing_list.getSubscription(member))

    def test_autoSubscribeToMailingList_without_preferredemail(self):
        # Users without preferred email addresses cannot subscribe.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        with person_logged_in(member):
            member.setPreferredEmail(None)
        subscribed = member.autoSubscribeToMailingList(team.mailing_list)
        self.assertIs(False, subscribed)
        self.assertIs(None, team.mailing_list.getSubscription(member))

    def test_autoSubscribeToMailingList_with_inactive_list(self):
        # Users cannot subscribe to inactive lists.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        with person_logged_in(team.teamowner):
            team.mailing_list.deactivate()
        subscribed = member.autoSubscribeToMailingList(team.mailing_list)
        self.assertIs(False, subscribed)
        self.assertIs(None, team.mailing_list.getSubscription(member))

    def test_autoSubscribeToMailingList_twice(self):
        # Users cannot subscribe twice.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        subscribed = member.autoSubscribeToMailingList(team.mailing_list)
        self.assertIs(True, subscribed)
        subscribed = member.autoSubscribeToMailingList(team.mailing_list)
        self.assertIs(False, subscribed)
        self.assertIsNot(None, team.mailing_list.getSubscription(member))


class MailingListTestCase(TestCaseWithFactory):
    """Tests for MailingList data and behaviour."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.team, self.mailing_list = self.factory.makeTeamAndMailingList(
            'test-mailinglist', 'team-owner')

    def test_subscribe_without_address(self):
        # An error is raised if subscribe() if a team is passed.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        team.mailing_list.subscribe(member)
        subscription = team.mailing_list.getSubscription(member)
        self.assertEqual(member, subscription.person)
        self.assertIs(None, subscription.email_address)

    def test_subscribe_with_address(self):
        # An error is raised if subscribe() if a team is passed.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        email = self.factory.makeEmail('him@eg.dom', member)
        team.mailing_list.subscribe(member, email)
        subscription = team.mailing_list.getSubscription(member)
        self.assertEqual(member, subscription.person)
        self.assertEqual(email, subscription.email_address)

    def test_subscribe_team_error(self):
        # An error is raised if subscribe() if a team is passed.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        other_team = self.factory.makeTeam()
        self.assertRaises(
            CannotSubscribe, team.mailing_list.subscribe, other_team)

    def test_subscribe_wrong_address_error(self):
        # An error is raised if subscribe() is called with an address that
        # does not belong to the user.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        email = self.factory.makeEmail('him@eg.dom', self.factory.makePerson())
        with person_logged_in(member):
            self.assertRaises(
                CannotSubscribe, team.mailing_list.subscribe, member, email)

    def test_subscribe_twice_error(self):
        # An error is raised if subscribe() is called with a user already
        # subscribed.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        team.mailing_list.subscribe(member)
        self.assertRaises(CannotSubscribe, team.mailing_list.subscribe, member)

    def test_subscribe_inactive_list_error(self):
        # An error is raised if subscribe() is called on an inactive list.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        with person_logged_in(team.teamowner):
            team.mailing_list.deactivate()
        self.assertRaises(CannotSubscribe, team.mailing_list.subscribe, member)

    def test_unsubscribe_deleted_email_address(self):
        # When a user delete an email address that use used by a
        # subscription, the user is implicitly unsubscibed.
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        email = self.factory.makeEmail('him@eg.dom', member)
        team.mailing_list.subscribe(member, email)
        with person_logged_in(member):
            email.destroySelf()
        self.assertIs(None, team.mailing_list.getSubscription(member))

    def test_getSubscribers_only_active_members_are_subscribers(self):
        former_member = self.factory.makePerson()
        pending_member = self.factory.makePerson()
        active_member = self.active_member = self.factory.makePerson()
        # Each of our members want to be subscribed to a team's mailing list
        # whenever they join the team.
        login_celebrity('admin')
        former_member.mailing_list_auto_subscribe_policy = (
            MailingListAutoSubscribePolicy.ALWAYS)
        active_member.mailing_list_auto_subscribe_policy = (
            MailingListAutoSubscribePolicy.ALWAYS)
        pending_member.mailing_list_auto_subscribe_policy = (
            MailingListAutoSubscribePolicy.ALWAYS)
        self.team.membership_policy = TeamMembershipPolicy.MODERATED
        pending_member.join(self.team)
        self.team.addMember(former_member, reviewer=self.team.teamowner)
        former_member.leave(self.team)
        self.team.addMember(active_member, reviewer=self.team.teamowner)
        # Even though our 3 members want to subscribe to the team's mailing
        # list, only the active member is considered a subscriber.
        self.assertEqual(
            [active_member], list(self.mailing_list.getSubscribers()))

    def test_getSubscribers_order(self):
        person_1 = self.factory.makePerson(name="pb1", displayname="Me")
        with person_logged_in(person_1):
            person_1.mailing_list_auto_subscribe_policy = (
                MailingListAutoSubscribePolicy.ALWAYS)
            person_1.join(self.team)
        person_2 = self.factory.makePerson(name="pa2", displayname="Me")
        with person_logged_in(person_2):
            person_2.mailing_list_auto_subscribe_policy = (
                MailingListAutoSubscribePolicy.ALWAYS)
            person_2.join(self.team)
        subscribers = self.mailing_list.getSubscribers()
        self.assertEqual(2, subscribers.count())
        self.assertEqual(
            ['pa2', 'pb1'], [person.name for person in subscribers])


class MailinglistSetTestCase(TestCaseWithFactory):
    """Test the mailing list set class."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(MailinglistSetTestCase, self).setUp()
        self.mailing_list_set = getUtility(IMailingListSet)
        login_celebrity('admin')

    def test_getSenderAddresses_dict_keys(self):
        # getSenderAddresses() returns a dict of teams names
        # {team_name: [(member_displayname, member_email) ...]}
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1', auto_subscribe=False)
        team2, member2 = self.factory.makeTeamWithMailingListSubscribers(
            'team2', auto_subscribe=False)
        team_names = [team1.name, team2.name]
        result = self.mailing_list_set.getSenderAddresses(team_names)
        self.assertEqual(team_names, sorted(result.keys()))

    def test_getSenderAddresses_dict_values(self):
        # getSenderAddresses() returns a dict of team namess with a list of
        # all membera display names and email addresses.
        # {team_name: [(member_displayname, member_email) ...]}
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1', auto_subscribe=False)
        result = self.mailing_list_set.getSenderAddresses([team1.name])
        list_senders = sorted([
            (m.displayname, m.preferredemail.email)
            for m in team1.allmembers])
        self.assertEqual(list_senders, sorted(result[team1.name]))

    def test_getSenderAddresses_multiple_and_lowercase_email(self):
        # getSenderAddresses() contains multiple email addresses for
        # users and they are lowercased for mailman.
        # {team_name: [(member_displayname, member_email) ...]}
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1', auto_subscribe=False)
        email = self.factory.makeEmail('me@EG.dom', member1)
        result = self.mailing_list_set.getSenderAddresses([team1.name])
        list_senders = sorted([
            (m.displayname, m.preferredemail.email)
            for m in team1.allmembers])
        list_senders.append((member1.displayname, email.email.lower()))
        self.assertContentEqual(list_senders, result[team1.name])

    def test_getSenderAddresses_participation_dict_values(self):
        # getSenderAddresses() dict values includes indirect participants.
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1', auto_subscribe=False)
        result = self.mailing_list_set.getSenderAddresses([team1.name])
        list_senders = sorted([
            (m.displayname, m.preferredemail.email)
            for m in team1.allmembers if m.preferredemail])
        self.assertEqual(list_senders, sorted(result[team1.name]))

    def test_getSenderAddresses_inactive_list(self):
        # Inactive lists are not include
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1', auto_subscribe=True)
        team2, member2 = self.factory.makeTeamWithMailingListSubscribers(
            'team2', auto_subscribe=True)
        with person_logged_in(team2.teamowner):
            team2.mailing_list.deactivate()
            team2.mailing_list.transitionToStatus(MailingListStatus.INACTIVE)
        team_names = [team1.name, team2.name]
        result = self.mailing_list_set.getSenderAddresses(team_names)
        self.assertEqual([team1.name], result.keys())

    def test_getSubscribedAddresses_dict_keys(self):
        # getSubscribedAddresses() returns a dict of team names.
        # {team_name: [(subscriber_displayname, subscriber_email) ...]}
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1')
        team2, member2 = self.factory.makeTeamWithMailingListSubscribers(
            'team2')
        team_names = [team1.name, team2.name]
        result = self.mailing_list_set.getSubscribedAddresses(team_names)
        self.assertEqual(team_names, sorted(result.keys()))

    def test_getSubscribedAddresses_dict_values(self):
        # getSubscribedAddresses() returns a dict of teams names with a list
        # of subscriber tuples.
        # {team_name: [(subscriber_displayname, subscriber_email) ...]}
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1')
        result = self.mailing_list_set.getSubscribedAddresses([team1.name])
        list_subscribers = [
            (member1.displayname, member1.preferredemail.email)]
        self.assertEqual(list_subscribers, result[team1.name])

    def test_getSubscribedAddresses_multiple_lowercase_email(self):
        # getSubscribedAddresses() contains email addresses for
        # users and they are lowercased for mailman. The email maybe
        # explicitly set instead of the preferred email.
        # {team_name: [(member_displayname, member_email) ...]}
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1')
        with person_logged_in(member1):
            email1 = self.factory.makeEmail('me@EG.dom', member1)
            member1.setPreferredEmail(email1)
        with person_logged_in(team1.teamowner):
            email2 = self.factory.makeEmail('you@EG.dom', team1.teamowner)
            team1.mailing_list.subscribe(team1.teamowner, email2)
        result = self.mailing_list_set.getSubscribedAddresses([team1.name])
        list_subscribers = [
            (member1.displayname, email1.email.lower()),
            (team1.teamowner.displayname, email2.email.lower())]
        self.assertContentEqual(list_subscribers, result[team1.name])

    def test_getSubscribedAddresses_participation_dict_values(self):
        # getSubscribedAddresses() dict values includes indirect participants.
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1')
        team2, member2 = self.factory.makeTeamWithMailingListSubscribers(
            'team2', super_team=team1)
        result = self.mailing_list_set.getSubscribedAddresses([team1.name])
        list_subscribers = sorted([
            (member1.displayname, member1.preferredemail.email),
            (member2.displayname, member2.preferredemail.email)])
        self.assertEqual(list_subscribers, sorted(result[team1.name]))

    def test_getSubscribedAddresses_preferredemail_dict_values(self):
        # getSubscribedAddresses() dict values include users who want email to
        # go to their preferred address.
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1', auto_subscribe=False)
        team1.mailing_list.subscribe(member1)
        result = self.mailing_list_set.getSubscribedAddresses([team1.name])
        list_subscribers = [
            (member1.displayname, member1.preferredemail.email)]
        self.assertEqual(list_subscribers, result[team1.name])

    def test_getSubscribedAddresses_inactive_list(self):
        # Inactive lists are not include
        team1, member1 = self.factory.makeTeamWithMailingListSubscribers(
            'team1', auto_subscribe=True)
        team2, member2 = self.factory.makeTeamWithMailingListSubscribers(
            'team2', auto_subscribe=True)
        with person_logged_in(team2.teamowner):
            team2.mailing_list.deactivate()
            team2.mailing_list.transitionToStatus(MailingListStatus.INACTIVE)
        team_names = [team1.name, team2.name]
        result = self.mailing_list_set.getSubscribedAddresses(team_names)
        self.assertEqual([team1.name], result.keys())


class MailingListMessageTestCase(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(MailingListMessageTestCase, self).setUp()
        self.mailing_list_set = getUtility(IMailingListSet)
        login_celebrity('admin')

    def makeMailingListAndHeldMessage(self):
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=True)
        sender = self.factory.makePerson()
        email = dedent(str("""\
            From: %s
            To: %s
            Subject: A question
            Message-ID: <first-post>
            Date: Fri, 01 Aug 2000 01:08:59 -0000\n
            I have a question about this team.
            """ % (sender.preferredemail.email, team.mailing_list.address)))
        message = getUtility(IMessageSet).fromEmail(email)
        held_message = team.mailing_list.holdMessage(message)
        transaction.commit()
        return team, member, sender, held_message


class MailingListHeldMessageTestCase(MailingListMessageTestCase):
    """Test the MailingList held message behaviour."""

    def test_holdMessage(self):
        # calling holdMessage() will create a held message and a notification.
        # The messages content is re-encoded
        team, member = self.factory.makeTeamWithMailingListSubscribers(
            'team', auto_subscribe=False)
        sender = self.factory.makePerson()
        email = dedent(str("""\
            From: %s
            To: %s
            Subject:  =?iso-8859-1?q?Adi=C3=B3s?=
            Message-ID: <first-post>
            Date: Fri, 01 Aug 2000 01:08:59 -0000\n
            hi.
            """ % (sender.preferredemail.email, team.mailing_list.address)))
        message = getUtility(IMessageSet).fromEmail(email)
        pop_notifications()
        held_message = team.mailing_list.holdMessage(message)
        self.assertEqual(PostedMessageStatus.NEW, held_message.status)
        self.assertEqual(message.rfc822msgid, held_message.message_id)
        notifications = pop_notifications()
        self.assertEqual(1, len(notifications))
        self.assertEqual(
            'New mailing list message requiring approval for Team',
            notifications[0]['subject'])
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '.*Subject: Adi=C3=83=C2=B3s.*', notifications[0].get_payload())

    def test_getReviewableMessages(self):
        # All the messages that need review can be retrieved.
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        held_messages = team.mailing_list.getReviewableMessages()
        self.assertEqual(1, held_messages.count())
        self.assertEqual(held_message.message_id, held_messages[0].message_id)


class MessageApprovalTestCase(MailingListMessageTestCase):
    """Test the MessageApproval data behaviour."""

    def test_mailinglistset_getSenderAddresses_approved_dict_values(self):
        # getSenderAddresses() dict values includes senders where were
        # approved in the list moderation queue.
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        held_message.approve(team.teamowner)
        result = self.mailing_list_set.getSenderAddresses([team.name])
        list_senders = sorted([
            (team.teamowner.displayname, team.teamowner.preferredemail.email),
            (member.displayname, member.preferredemail.email),
            (sender.displayname, sender.preferredemail.email)])
        self.assertEqual(list_senders, sorted(result[team.name]))

    def test_new_state(self):
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        self.assertEqual(PostedMessageStatus.NEW, held_message.status)
        self.assertIs(None, held_message.disposed_by)
        self.assertIs(None, held_message.disposal_date)
        self.assertEqual(sender, held_message.posted_by)
        self.assertEqual(team.mailing_list, held_message.mailing_list)
        self.assertEqual('<first-post>', held_message.message.rfc822msgid)
        self.assertEqual(
            held_message.message.datecreated, held_message.posted_date)
        try:
            held_message.posted_message.open()
            text = held_message.posted_message.read()
        finally:
            held_message.posted_message.close()
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '.*Message-ID: <first-post>.*', text)

    def test_approve(self):
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        held_message.approve(team.teamowner)
        self.assertEqual(
            PostedMessageStatus.APPROVAL_PENDING, held_message.status)
        self.assertEqual(team.teamowner, held_message.disposed_by)
        self.assertIsNot(None, held_message.disposal_date)

    def test_reject(self):
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        held_message.reject(team.teamowner)
        self.assertEqual(
            PostedMessageStatus.REJECTION_PENDING, held_message.status)
        self.assertEqual(team.teamowner, held_message.disposed_by)
        self.assertIsNot(None, held_message.disposal_date)

    def test_discad(self):
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        held_message.discard(team.teamowner)
        self.assertEqual(
            PostedMessageStatus.DISCARD_PENDING, held_message.status)
        self.assertEqual(team.teamowner, held_message.disposed_by)
        self.assertIsNot(None, held_message.disposal_date)

    def test_acknowledge(self):
        # The acknowledge method changes the pending status to the
        # final status.
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        held_message.discard(team.teamowner)
        self.assertEqual(
            PostedMessageStatus.DISCARD_PENDING, held_message.status)
        held_message.acknowledge()
        self.assertEqual(
            PostedMessageStatus.DISCARDED, held_message.status)


class MessageApprovalSetTestCase(MailingListMessageTestCase):
    """Test the MessageApprovalSet behaviour."""

    def test_getMessageByMessageID(self):
        # held Messages can be looked up by rfc822 messsge id.
        held_message = self.makeMailingListAndHeldMessage()[-1]
        message_approval_set = getUtility(IMessageApprovalSet)
        found_message = message_approval_set.getMessageByMessageID(
            held_message.message_id)
        self.assertEqual(held_message.message_id, found_message.message_id)

    def test_getHeldMessagesWithStatus(self):
        # Messages can be retrieved by status.
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        message_approval_set = getUtility(IMessageApprovalSet)
        found_messages = message_approval_set.getHeldMessagesWithStatus(
            PostedMessageStatus.NEW)
        self.assertEqual(1, found_messages.count())
        self.assertEqual(
            (held_message.message_id, team.name), found_messages[0])

    def test_acknowledgeMessagesWithStatus(self):
        # Message statuses can be updated from pending states to final states.
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        held_message.approve(team.teamowner)
        self.assertEqual(
            PostedMessageStatus.APPROVAL_PENDING, held_message.status)
        message_approval_set = getUtility(IMessageApprovalSet)
        message_approval_set.acknowledgeMessagesWithStatus(
            PostedMessageStatus.APPROVAL_PENDING)
        self.assertEqual(PostedMessageStatus.APPROVED, held_message.status)


class HeldMessageDetailsTestCase(MailingListMessageTestCase):
    """Test the HeldMessageDetails data."""

    def test_attributes(self):
        held_message = self.makeMailingListAndHeldMessage()[-1]
        details = IHeldMessageDetails(held_message)
        self.assertEqual(held_message, details.message_approval)
        self.assertEqual(held_message.message, details.message)
        self.assertEqual(held_message.message_id, details.message_id)
        self.assertEqual(held_message.message.subject, details.subject)
        self.assertEqual(held_message.message.datecreated, details.date)
        self.assertEqual(held_message.message.owner, details.author)

    def test_email_message(self):
        held_message = self.makeMailingListAndHeldMessage()[-1]
        details = IHeldMessageDetails(held_message)
        self.assertEqual('A question', details.email_message['subject'])

    def test_sender(self):
        test_objects = self.makeMailingListAndHeldMessage()
        team, member, sender, held_message = test_objects
        details = IHeldMessageDetails(held_message)
        self.assertEqual(sender.preferredemail.email, details.sender)

    def test_body(self):
        held_message = self.makeMailingListAndHeldMessage()[-1]
        details = IHeldMessageDetails(held_message)
        self.assertEqual(
            'I have a question about this team.', details.body.strip())
