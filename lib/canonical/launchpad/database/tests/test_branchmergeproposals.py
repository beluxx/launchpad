# Copyright 2008 Canonical Ltd.  All rights reserved.

"""Tests for BranchMergeProposals."""

__metaclass__ = type

from unittest import TestCase, TestLoader

from canonical.launchpad.database import BranchMergeProposalGetter
from canonical.launchpad.interfaces import WrongBranchMergeProposal
from canonical.launchpad.event import SQLObjectCreatedEvent
from canonical.launchpad.ftests import ANONYMOUS, login, logout, syncUpdate
from canonical.launchpad.interfaces import (
    BadStateTransition, BranchMergeProposalStatus,
    BranchSubscriptionNotificationLevel, CodeReviewNotificationLevel,
    EmailAddressStatus)
from canonical.launchpad.testing import (
     LaunchpadObjectFactory, TestCaseWithFactory, time_counter)

from canonical.testing import LaunchpadFunctionalLayer


class TestBranchMergeProposalTransitions(TestCase):
    """Test the state transitions of branch merge proposals."""

    layer = LaunchpadFunctionalLayer

    # All transitions between states are handled my method calls
    # on the proposal.
    transition_functions = {
        BranchMergeProposalStatus.WORK_IN_PROGRESS: 'setAsWorkInProgress',
        BranchMergeProposalStatus.NEEDS_REVIEW: 'requestReview',
        BranchMergeProposalStatus.CODE_APPROVED: 'approveBranch',
        BranchMergeProposalStatus.REJECTED: 'rejectBranch',
        BranchMergeProposalStatus.MERGED: 'markAsMerged',
        BranchMergeProposalStatus.MERGE_FAILED: 'mergeFailed',
        BranchMergeProposalStatus.QUEUED: 'enqueue',
        BranchMergeProposalStatus.SUPERSEDED: 'resubmit',
        }

    def setUp(self):
        TestCase.setUp(self)
        login(ANONYMOUS)
        self.factory = LaunchpadObjectFactory()
        owner = self.factory.makePerson(
            email_address_status=EmailAddressStatus.VALIDATED)
        self.target_branch = self.factory.makeBranch(owner=owner)
        login(self.target_branch.owner.preferredemail.email)

    def assertProposalState(self, proposal, state):
        """Assert that the `queue_status` of the `proposal` is `state`."""
        self.assertEqual(state, proposal.queue_status,
                         "Wrong state, expected %s, got %s"
                         % (state.title, proposal.queue_status.title))

    def _attemptTransition(self, proposal, to_state):
        """Try to transition the proposal into the state `to_state`."""
        method = getattr(proposal, self.transition_functions[to_state])
        if to_state in (BranchMergeProposalStatus.CODE_APPROVED,
                        BranchMergeProposalStatus.REJECTED,
                        BranchMergeProposalStatus.QUEUED):
            args = [proposal.target_branch.owner, 'some_revision_id']
        elif to_state in (BranchMergeProposalStatus.MERGE_FAILED,
                          BranchMergeProposalStatus.SUPERSEDED):
            args = [proposal.registrant]
        else:
            args = []
        method(*args)

    def assertGoodTransition(self, from_state, to_state):
        """Assert that we can go from `from_state` to `to_state`."""
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=from_state)
        self.assertProposalState(proposal, from_state)
        self._attemptTransition(proposal, to_state)
        self.assertProposalState(proposal, to_state)

    def assertBadTransition(self, from_state, to_state):
        """Assert that trying to go from `from_state` to `to_state` fails."""
        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch,
            set_state=from_state)
        self.assertProposalState(proposal, from_state)
        self.assertRaises(BadStateTransition,
                          self._attemptTransition,
                          proposal, to_state)

    def assertAllTransitionsGood(self, from_state):
        """Assert that we can go from `from_state` to any state."""
        for status in BranchMergeProposalStatus.items:
            self.assertGoodTransition(from_state, status)

    def assertTerminatingState(self, from_state):
        """Assert that the proposal cannot go to any other state."""
        for status in BranchMergeProposalStatus.items:
            self.assertBadTransition(from_state, status)

    def test_transitions_from_wip(self):
        """We can go from work in progress to any other state."""
        self.assertAllTransitionsGood(
            BranchMergeProposalStatus.WORK_IN_PROGRESS)

    def test_transitions_from_needs_review(self):
        """We can go from needs review to any other state."""
        self.assertAllTransitionsGood(
            BranchMergeProposalStatus.NEEDS_REVIEW)

    def test_transitions_from_code_approved(self):
        """We can go from code_approved to any other state."""
        self.assertAllTransitionsGood(
            BranchMergeProposalStatus.CODE_APPROVED)

    def test_transitions_from_rejected(self):
        """Rejected proposals can only be resubmitted."""
        # Test the transitions from rejected.
        [wip, needs_review, code_approved, rejected,
         merged, merge_failed, queued, superseded
         ] = BranchMergeProposalStatus.items

        for status in (wip, needs_review, code_approved, rejected,
                       merged, queued, merge_failed):
            # All bad, rejected is a final state.
            self.assertBadTransition(rejected, status)
        # Can resubmit (supersede) a rejected proposal.
        self.assertGoodTransition(rejected, superseded)

    def test_transitions_from_merged(self):
        """Merged is a terminal state, so no transitions are valid."""
        self.assertTerminatingState(BranchMergeProposalStatus.MERGED)

    def test_transitions_from_merge_failed(self):
        """We can go from merge failed to any other state."""
        self.assertAllTransitionsGood(BranchMergeProposalStatus.MERGE_FAILED)

    def test_transitions_from_queued(self):
        """Queued proposals can only be marked as merged or merge failed.
        Queued proposals can be moved out of the queue using the `dequeue`
        method, and no other transitions are valid.
        """
        queued = BranchMergeProposalStatus.QUEUED
        for status in BranchMergeProposalStatus.items:
            if status in (BranchMergeProposalStatus.MERGED,
                          BranchMergeProposalStatus.MERGE_FAILED):
                self.assertGoodTransition(queued, status)
            else:
                self.assertBadTransition(queued, status)

        proposal = self.factory.makeBranchMergeProposal(
            target_branch=self.target_branch, set_state=queued)
        proposal.dequeue()
        self.assertProposalState(
            proposal, BranchMergeProposalStatus.CODE_APPROVED)

    def test_transitions_from_superseded(self):
        """Superseded is a terminal state, so no transitions are valid."""
        self.assertTerminatingState(BranchMergeProposalStatus.SUPERSEDED)

    def test_valid_transition_graph_is_complete(self):
        """The valid transition graph should have a key for all possible
        queue states."""
        from canonical.launchpad.database.branchmergeproposal import (
            VALID_TRANSITION_GRAPH)
        keys = VALID_TRANSITION_GRAPH.keys()
        all_states = BranchMergeProposalStatus.items
        self.assertEqual(sorted(all_states), sorted(keys),
                         "Missing possible states from the transition graph.")

class TestBranchMergeProposalCanReview(TestCase):
    """Test the different cases that makes a branch deletable or not."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        login('test@canonical.com')

        factory = LaunchpadObjectFactory()
        self.source_branch = factory.makeBranch()
        self.target_branch = factory.makeBranch(
            product=self.source_branch.product)
        registrant = factory.makePerson()
        self.proposal = self.source_branch.addLandingTarget(
            registrant, self.target_branch)

    def tearDown(self):
        logout()

    def test_validReviewer(self):
        """A newly created branch can be deleted without any problems."""
        self.assertEqual(self.proposal.isPersonValidReviewer(None),
                         False, "No user cannot review code")
        # The owner of the target branch is a valid reviewer.
        self.assertEqual(
            self.proposal.isPersonValidReviewer(
                self.target_branch.owner),
            True, "No user cannot review code")


class TestBranchMergeProposalQueueing(TestCase):
    """Test the enqueueing and dequeueing of merge proposals."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        TestCase.setUp(self)
        login(ANONYMOUS)
        factory = LaunchpadObjectFactory()
        owner = factory.makePerson(
            email_address_status=EmailAddressStatus.VALIDATED)
        self.target_branch = factory.makeBranch(owner=owner)
        login(self.target_branch.owner.preferredemail.email)
        self.proposals = [
            factory.makeBranchMergeProposal(self.target_branch)
            for x in range(4)]

    def test_empty_target_queue(self):
        """If there are no proposals targetted to the branch, the queue has
        nothing in it."""
        queued_proposals = list(self.target_branch.getMergeQueue())
        self.assertEqual(0, len(queued_proposals),
                         "The initial merge queue should be empty.")

    def test_single_item_in_queue(self):
        """Enqueing a proposal makes it visible in the target branch queue."""
        proposal = self.proposals[0]
        proposal.enqueue(self.target_branch.owner, 'some-revision-id')
        queued_proposals = list(self.target_branch.getMergeQueue())
        self.assertEqual(1, len(queued_proposals),
                         "Should have one entry in the queue, got %s."
                         % len(queued_proposals))

    def test_queue_ordering(self):
        """Assert that the queue positions are based on the order the
        proposals were enqueued."""
        enqueued_order = []
        for proposal in self.proposals[:-1]:
            enqueued_order.append(proposal.source_branch.unique_name)
            proposal.enqueue(self.target_branch.owner, 'some-revision')
        queued_proposals = list(self.target_branch.getMergeQueue())
        queue_order = [proposal.source_branch.unique_name
                       for proposal in queued_proposals]
        self.assertEqual(
            enqueued_order, queue_order,
            "The queue should be in the order they were added. "
            "Expected %s, got %s" % (enqueued_order, queue_order))

        # Move the last one to the front.
        proposal = queued_proposals[-1]
        proposal.moveToFrontOfQueue()

        new_queue_order = enqueued_order[-1:] + enqueued_order[:-1]

        queued_proposals = list(self.target_branch.getMergeQueue())
        queue_order = [proposal.source_branch.unique_name
                       for proposal in queued_proposals]
        self.assertEqual(
            new_queue_order, queue_order,
            "The last should now be at the front. "
            "Expected %s, got %s" % (new_queue_order, queue_order))

        # Remove the proposal from the middle of the queue.
        proposal = queued_proposals[1]
        proposal.dequeue()
        syncUpdate(proposal)

        del new_queue_order[1]

        queued_proposals = list(self.target_branch.getMergeQueue())
        queue_order = [proposal.source_branch.unique_name
                       for proposal in queued_proposals]
        self.assertEqual(
            new_queue_order, queue_order,
            "There should be only two queued items now. "
            "Expected %s, got %s" % (new_queue_order, queue_order))


class TestRootMessage(TestCase):
    """Test the behavior of the root_message attribute"""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        TestCase.setUp(self)
        login('foo.bar@canonical.com')
        self.factory = LaunchpadObjectFactory()
        self.merge_proposal = self.factory.makeBranchMergeProposal()

    def test_orderedByDateNotInsertion(self):
        """Root is determined by create date, not insert order"""
        counter = time_counter()
        oldest_date, middle_date, newest_date = [counter.next() for index in
            (1, 2, 3)]
        message1 = self.merge_proposal.createMessage(
            self.merge_proposal.registrant, "Subject",
            _date_created=middle_date)
        self.assertEqual(message1, self.merge_proposal.root_message)
        message2 = self.merge_proposal.createMessage(
            self.merge_proposal.registrant, "Subject",
            _date_created=newest_date)
        self.assertEqual(message1, self.merge_proposal.root_message)
        message3 = self.merge_proposal.createMessage(
            self.merge_proposal.registrant, "Subject",
            _date_created=oldest_date)
        self.assertEqual(message3, self.merge_proposal.root_message)


class TestMergeProposalAllMessages(TestCase):
    """Tester for `BranchMergeProposal.all_messages`."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        TestCase.setUp(self)
        # Testing behavior, not permissions here.
        login('foo.bar@canonical.com')
        self.factory = LaunchpadObjectFactory()
        self.merge_proposal = self.factory.makeBranchMergeProposal()

    def test_all_messages(self):
        """Ensure all messages associated with the proposal are returned."""
        message1 = self.merge_proposal.createMessage(
            self.merge_proposal.registrant, "Subject")
        message2 = self.merge_proposal.createMessage(
            self.merge_proposal.registrant, "Subject")
        message3 = self.merge_proposal.createMessage(
            self.merge_proposal.registrant, "Subject")
        self.assertEqual(
            set([message1, message2, message3]),
            set(self.merge_proposal.all_messages))


class TestMergeProposalGetMessage(TestCase):
    """Tester for `BranchMergeProposal.getMessage`."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        TestCase.setUp(self)
        # Testing behavior, not permissions here.
        login('foo.bar@canonical.com')
        self.factory = LaunchpadObjectFactory()
        self.merge_proposal = self.factory.makeBranchMergeProposal()
        self.merge_proposal2 = self.factory.makeBranchMergeProposal()
        self.message = self.merge_proposal.createMessage(
            self.merge_proposal.registrant, "Subject")

    def test_getMessage(self):
        """Tests that we can get a message."""
        self.assertEqual(
            self.message, self.merge_proposal.getMessage(self.message.id))

    def test_getMessageWrongBranchMergeProposal(self):
        """Tests that we can get a message."""
        self.assertRaises(WrongBranchMergeProposal,
                          self.merge_proposal2.getMessage, self.message.id)


class TestMergeProposalNotification(TestCaseWithFactory):
    """Test that events are created when merge proposals are manipulated"""

    layer = LaunchpadFunctionalLayer

    def test_notifyOnCreate(self):
        """Ensure that a notification is emitted on creation"""
        source_branch = self.factory.makeBranch()
        target_branch = self.factory.makeBranch(product=source_branch.product)
        registrant = self.factory.makePerson()
        result, event = self.assertNotifies(SQLObjectCreatedEvent,
            source_branch.addLandingTarget, registrant, target_branch)
        self.assertEqual(result, event.object)

    def test_getNotificationRecipients(self):
        """Ensure that recipients can be added/removed with subscribe"""
        bmp = self.factory.makeBranchMergeProposal()
        self.assertEqual({},
            bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.STATUS))
        source_subscriber = self.factory.makePerson()
        bmp.source_branch.subscribe(source_subscriber,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL)
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.STATUS)
        self.assertEqual([source_subscriber], recipients.keys())
        bmp.source_branch.subscribe(source_subscriber,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.NOEMAIL)
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.STATUS)
        self.assertEqual([], recipients.keys())

    def test_getNotificationRecipientLevels(self):
        """Ensure that only recipients with the right level are returned"""
        bmp = self.factory.makeBranchMergeProposal()
        full_subscriber = self.factory.makePerson()
        bmp.source_branch.subscribe(full_subscriber,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL)
        status_subscriber = self.factory.makePerson()
        bmp.source_branch.subscribe(status_subscriber,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.STATUS)
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.STATUS)
        self.assertEqual(set([full_subscriber, status_subscriber]),
            set(recipients.keys()))
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.FULL)
        self.assertEqual([full_subscriber], recipients.keys())

    def test_getNotificationRecipientsAnyBranch(self):
        dependent_branch = self.factory.makeBranch()
        bmp = self.factory.makeBranchMergeProposal(
            dependent_branch=dependent_branch)
        self.assertEqual({},
        bmp.getNotificationRecipients(
            BranchSubscriptionNotificationLevel.NOEMAIL))
        source_subscriber = self.factory.makePerson()
        bmp.source_branch.subscribe(source_subscriber,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL)
        target_subscriber = self.factory.makePerson()
        bmp.target_branch.subscribe(target_subscriber,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL)
        dependent_subscriber = self.factory.makePerson()
        bmp.dependent_branch.subscribe(dependent_subscriber,
            BranchSubscriptionNotificationLevel.NOEMAIL, None,
            CodeReviewNotificationLevel.FULL)
        recipients = bmp.getNotificationRecipients(
            CodeReviewNotificationLevel.FULL)
        self.assertEqual(
            set([source_subscriber, target_subscriber, dependent_subscriber]),
            set(recipients.keys()))


class TestGetAddress(TestCaseWithFactory):
    """Test that the address property gives expected results."""

    layer = LaunchpadFunctionalLayer

    def test_address(self):
        merge_proposal = self.factory.makeBranchMergeProposal()
        expected = 'mp+%d@code.launchpad.dev' % merge_proposal.id
        self.assertEqual(expected, merge_proposal.address)


class TestBranchMergeProposalGetter(TestCaseWithFactory):
    """Test that the BranchMergeProposalGetter behaves as expected."""

    layer = LaunchpadFunctionalLayer

    def test_get(self):
        """Ensure the correct merge proposal is returned."""
        merge_proposal = self.factory.makeBranchMergeProposal()
        self.assertEqual(merge_proposal,
            BranchMergeProposalGetter().get(merge_proposal.id))


def test_suite():
    return TestLoader().loadTestsFromName(__name__)
