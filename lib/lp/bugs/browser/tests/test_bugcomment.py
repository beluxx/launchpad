# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the bugcomment module."""

__metaclass__ = type

from datetime import (
    datetime,
    timedelta,
    )
from itertools import count

from pytz import utc
from zope.component import getUtility

from canonical.launchpad.interfaces.launchpad import ILaunchpadCelebrities
from canonical.launchpad.testing.pages import find_tag_by_id
from canonical.testing.layers import DatabaseFunctionalLayer
from lp.bugs.browser.bugcomment import group_comments_with_activity
from lp.testing import (
    BrowserTestCase,
    person_logged_in,
    TestCase,
    )


class BugActivityStub:

    def __init__(self, datechanged, owner=None):
        self.datechanged = datechanged
        if owner is None:
            owner = PersonStub()
        self.person = owner

    def __repr__(self):
        return "BugActivityStub(%r, %r)" % (
            self.datechanged.strftime('%Y-%m-%d--%H%M'), self.person)


class BugCommentStub:

    def __init__(self, datecreated, index, owner=None):
        self.datecreated = datecreated
        if owner is None:
            owner = PersonStub()
        self.owner = owner
        self.activity = []
        self.index = index

    def __repr__(self):
        return "BugCommentStub(%r, %d, %r)" % (
            self.datecreated.strftime('%Y-%m-%d--%H%M'),
            self.index, self.owner)


class PersonStub:

    ids = count(1)

    def __init__(self):
        self.id = next(self.ids)

    def __repr__(self):
        return "PersonStub#%d" % self.id


class TestGroupCommentsWithActivities(TestCase):
    """Tests for `group_comments_with_activities`."""

    def setUp(self):
        super(TestGroupCommentsWithActivities, self).setUp()
        self.now = datetime.now(utc)
        self.time_index = (
            (self.now + timedelta(minutes=counter), counter)
            for counter in count(1))

    def group(self, comments, activities):
        return list(
            group_comments_with_activity(
                comments=comments, activities=activities))

    def test_empty(self):
        # Given no comments or activities the result is also empty.
        self.assertEqual(
            [], self.group(comments=[], activities=[]))

    def test_activity_empty_no_common_actor(self):
        # When no activities are passed in, and the comments passed in don't
        # have any common actors, no grouping is possible.
        comments = [
            BugCommentStub(*next(self.time_index))
            for number in xrange(5)]
        self.assertEqual(
            comments, self.group(comments=comments, activities=[]))

    def test_comments_empty_no_common_actor(self):
        # When no comments are passed in, and the activities passed in don't
        # have any common actors, no grouping is possible.
        activities = [
            BugActivityStub(next(self.time_index)[0])
            for number in xrange(5)]
        self.assertEqual(
            [[activity] for activity in activities], self.group(
                comments=[], activities=activities))

    def test_no_common_actor(self):
        # When each activities and comment given has a different actor then no
        # grouping is possible.
        activity1 = BugActivityStub(next(self.time_index)[0])
        comment1 = BugCommentStub(*next(self.time_index))
        activity2 = BugActivityStub(next(self.time_index)[0])
        comment2 = BugCommentStub(*next(self.time_index))

        activities = set([activity1, activity2])
        comments = list([comment1, comment2])

        self.assertEqual(
            [[activity1], comment1, [activity2], comment2],
            self.group(comments=comments, activities=activities))

    def test_comment_then_activity_close_by_common_actor(self):
        # An activity shortly after a comment by the same person is grouped
        # into the comment.
        actor = PersonStub()
        comment = BugCommentStub(*next(self.time_index), owner=actor)
        activity = BugActivityStub(next(self.time_index)[0], owner=actor)
        grouped = self.group(comments=[comment], activities=[activity])
        self.assertEqual([comment], grouped)
        self.assertEqual([activity], comment.activity)

    def test_activity_then_comment_close_by_common_actor(self):
        # An activity shortly before a comment by the same person is grouped
        # into the comment.
        actor = PersonStub()
        activity = BugActivityStub(next(self.time_index)[0], owner=actor)
        comment = BugCommentStub(*next(self.time_index), owner=actor)
        grouped = self.group(comments=[comment], activities=[activity])
        self.assertEqual([comment], grouped)
        self.assertEqual([activity], comment.activity)

    def test_interleaved_activity_with_comment_by_common_actor(self):
        # Activities shortly before and after a comment are grouped into the
        # comment's activity.
        actor = PersonStub()
        activity1 = BugActivityStub(next(self.time_index)[0], owner=actor)
        comment = BugCommentStub(*next(self.time_index), owner=actor)
        activity2 = BugActivityStub(next(self.time_index)[0], owner=actor)
        grouped = self.group(
            comments=[comment], activities=[activity1, activity2])
        self.assertEqual([comment], grouped)
        self.assertEqual([activity1, activity2], comment.activity)

    def test_common_actor_over_a_prolonged_time(self):
        # There is a timeframe for grouping events, 5 minutes by default.
        # Anything outside of that window is considered separate.
        actor = PersonStub()
        activities = [
            BugActivityStub(next(self.time_index)[0], owner=actor)
            for count in xrange(8)]
        grouped = self.group(comments=[], activities=activities)
        self.assertEqual(2, len(grouped))
        self.assertEqual(activities[:5], grouped[0])
        self.assertEqual(activities[5:], grouped[1])

    def test_two_comments_by_common_actor(self):
        # Only one comment will ever appear in a group.
        actor = PersonStub()
        comment1 = BugCommentStub(*next(self.time_index), owner=actor)
        comment2 = BugCommentStub(*next(self.time_index), owner=actor)
        grouped = self.group(comments=[comment1, comment2], activities=[])
        self.assertEqual([comment1, comment2], grouped)

    def test_two_comments_with_activity_by_common_actor(self):
        # Activity gets associated with earlier comment when all other factors
        # are unchanging.
        actor = PersonStub()
        activity1 = BugActivityStub(next(self.time_index)[0], owner=actor)
        comment1 = BugCommentStub(*next(self.time_index), owner=actor)
        activity2 = BugActivityStub(next(self.time_index)[0], owner=actor)
        comment2 = BugCommentStub(*next(self.time_index), owner=actor)
        activity3 = BugActivityStub(next(self.time_index)[0], owner=actor)
        grouped = self.group(
            comments=[comment1, comment2],
            activities=[activity1, activity2, activity3])
        self.assertEqual([comment1, comment2], grouped)
        self.assertEqual([activity1, activity2], comment1.activity)
        self.assertEqual([activity3], comment2.activity)


class TestBugCommentVisibility(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def makeBugWithHiddenComment(self, bugbody=None):
        administrator = getUtility(ILaunchpadCelebrities).admin.teamowner
        bug = self.factory.makeBug()
        with person_logged_in(administrator):
            comment = self.factory.makeBugComment(bug=bug, body=bugbody)
            comment.visible = False
        return bug

    def test_admin_can_see_comments(self):
        comment_text = "You can't see me."
        bug = self.makeBugWithHiddenComment(comment_text)
        admin = self.factory.makeAdministrator()
        view = self.getViewBrowser(
            context=bug.default_bugtask, user=admin)
        self.assertTrue(
           comment_text in view.contents,
           "Administrator cannot see the hidden comment.")

    def test_registry_can_see_comments(self):
        comment_text = "You can't see me."
        bug = self.makeBugWithHiddenComment(comment_text)
        registry_expert = self.factory.makeRegistryExpert()
        view = self.getViewBrowser(
            context=bug.default_bugtask, user=registry_expert)
        self.assertTrue(
           comment_text in view.contents,
           "Registy member cannot see the hidden comment.")

    def test_anon_cannot_see_comments(self):
        comment_text = "You can't see me."
        bug = self.makeBugWithHiddenComment(comment_text)
        view = self.getViewBrowser(context=bug.default_bugtask, no_login=True)
        self.assertFalse(
           comment_text in view.contents,
           "Anonymous person can see the hidden comment.")

    def test_random_cannot_see_comments(self):
        comment_text = "You can't see me."
        bug = self.makeBugWithHiddenComment(comment_text)
        view = self.getViewBrowser(context=bug.default_bugtask)
        self.assertFalse(
           comment_text in view.contents,
           "Random user can see the hidden comment.")


class TestBugSpamControls(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def makeBugWithComment(self, bugbody=None):
        administrator = getUtility(ILaunchpadCelebrities).admin.teamowner
        bug = self.factory.makeBug()
        with person_logged_in(administrator):
            self.factory.makeBugComment(bug=bug, body=bugbody)
        return bug

    def test_admin_sees_spam_control(self):
        bug = self.makeBugWithComment()
        administrator = self.factory.makeAdministrator()
        view = self.getViewBrowser(context=bug, user=administrator)
        spam_link = find_tag_by_id(view.contents, 'mark-spam-1')
        self.assertIsNot(None, spam_link)

    def test_registry_sees_spam_control(self):
        bug = self.makeBugWithComment()
        registry_expert = self.factory.makeRegistryExpert()
        view = self.getViewBrowser(context=bug, user=registry_expert)
        spam_link = find_tag_by_id(view.contents, 'mark-spam-1')
        self.assertIsNot(None, spam_link)

    def test_anon_doesnt_see_spam_control(self):
        bug = self.makeBugWithComment()
        view = self.getViewBrowser(context=bug, no_login=True)
        spam_link = find_tag_by_id(view.contents, 'mark-spam-1')
        self.assertIs(None, spam_link)

    def test_random_doesnt_see_spam_control(self):
        bug = self.makeBugWithComment()
        view = self.getViewBrowser(context=bug)
        spam_link = find_tag_by_id(view.contents, 'mark-spam-1')
        self.assertIs(None, spam_link)
