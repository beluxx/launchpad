# Copyright 2004 Canonical Ltd.  All rights reserved.

""" karma.py -- handles all karma assignments done in the launchpad 
application."""

from zope.component import getUtility

from canonical.launchpad.interfaces import IPersonSet
from canonical.launchpad.mailnotification import get_bug_delta, get_task_delta
from canonical.lp.dbschema import (BugTaskStatus, KarmaActionName,
     RosettaImportStatus)


def bug_created(bug, event):
    """Assign karma to the user which created <bug>."""
    bug.owner.assignKarma(KarmaActionName.BUGCREATED)


def bugtask_created(bug, event):
    """Assign karma to the user which created <bugtask>."""
    bug.owner.assignKarma(KarmaActionName.BUGTASKCREATED)


def bug_comment_added(bugmessage, event):
    """Assign karma to the user which added <bugmessage>."""
    bugmessage.message.owner.assignKarma(KarmaActionName.BUGCOMMENTADDED)


def bug_modified(bug, event):
    """Check changes made to <bug> and assign karma to user if needed."""
    user = event.user
    bug_delta = get_bug_delta(
        event.object_before_modification, event.object, user)

    attrs_actionnames = {'title': KarmaActionName.BUGTITLECHANGED,
                         'summary': KarmaActionName.BUGSUMMARYCHANGED,
                         'description': KarmaActionName.BUGDESCRIPTIONCHANGED,
                         'external_reference': KarmaActionName.BUGEXTREFCHANGED,
                         'cveref': KarmaActionName.BUGCVEREFCHANGED}

    for attr, actionname in attrs_actionnames.items():
        if getattr(bug_delta, attr) is not None:
            user.assignKarma(actionname)


def bugtask_modified(bugtask, event):
    """Check changes made to <bugtask> and assign karma to user if needed."""
    user = event.user
    task_delta = get_task_delta(event.object_before_modification, event.object)

    if (task_delta.status is not None and 
        task_delta.status['new'] == BugTaskStatus.FIXED):
        user.assignKarma(KarmaActionName.BUGFIXED)

def potemplate_modified(template, event):
    """Check changes made to <template> and assign karma to user if needed."""
    user = event.user
    old = event.object_before_modification
    new = event.object

    if old.description != new.description:
        user.assignKarma(
            KarmaActionName.TRANSLATIONTEMPLATEDESCRIPTIONCHANGED)

    if (old.rawimportstatus != new.rawimportstatus and
        new.rawimportstatus == RosettaImportStatus.IMPORTED):
        # A new .pot file has been imported. The karma goes to the one that
        # attached the file.
        new.rawimporter.assignKarma(
            KarmaActionName.TRANSLATIONTEMPLATEIMPORT)

def pofile_modified(pofile, event):
    """Check changes made to <pofile> and assign karma to user if needed."""
    user = event.user
    old = event.object_before_modification
    new = event.object

    if (old.rawimportstatus != new.rawimportstatus and
        new.rawimportstatus == RosettaImportStatus.IMPORTED and
        new.rawfilepublished):
        # A new .po file from upstream has been imported. The karma goes to
        # the one that attached the file.
        new.rawimporter.assignKarma(
            KarmaActionName.TRANSLATIONIMPORTUPSTREAM)

def posubmission_created(submission, event):
    """Assign karma to the user which created <submission>."""
    if submission.person is not None:
        submission.person.assignKarma(
            KarmaActionName.TRANSLATIONSUGGESTIONADDED)


def poselection_created(selection, event):
    """Assign karma to the submission author and the reviewer."""
    reviewer = event.user
    active = selection.activesubmission

    if (active is not None and
        active.person is not None and
        reviewer != active.person):
        # Only add Karma when you are not reviewing your own translations.
        active.person.assignKarma(KarmaActionName.TRANSLATIONSUGGESTIONAPPROVED)
        reviewer.assignKarma(KarmaActionName.TRANSLATIONREVIEW)


def poselection_modified(selection, event):
    """Assign karma to the submission author and the reviewer."""
    reviewer = event.user
    old = event.object_before_modification
    new = event.object

    if (old.activesubmission != new.activesubmission and
        new.activesubmission is not None and
        new.activesubmission.person is not None and
        reviewer != new.activesubmission.person):
        # Only add Karma when you are not reviewing your own translations.
        new.activesubmission.person.assignKarma(
            KarmaActionName.TRANSLATIONSUGGESTIONAPPROVED)
        if reviewer is not None:
            reviewer.assignKarma(KarmaActionName.TRANSLATIONREVIEW)
