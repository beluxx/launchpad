# Copyright 2008 Canonical Ltd.  All rights reserved.
# pylint: disable-msg=E0211,E0213

"""Interfaces including and related to IDiff."""

__metaclass__ = type

__all__ = [
    'IDiff',
    'IPreviewDiff',
    'IStaticDiff',
    'IStaticDiffSource',
    ]

from zope.schema import Bool, Object, Int, Text, TextLine
from zope.interface import Interface

from canonical.launchpad import _
from canonical.launchpad.interfaces.librarian import ILibraryFileAlias


class IDiff(Interface):
    """A diff that is stored in the Library."""

    text = Text(title=_('Textual contents of a diff.'))

    diff_text = Object(
        title=_('Content of this diff'), required=True,
        schema=ILibraryFileAlias)

    diff_lines_count = Int(
        title=_('The number of lines in this diff.'))

    diffstat = Text(title=_('Statistics about this diff'))

    added_lines_count = Int(
        title=_('The number of lines added in this diff.'))

    removed_lines_count = Int(
        title=_('The number of lines removed in this diff.'))


class IStaticDiff(Interface):
    """A diff with a fixed value, i.e. between two revisions."""

    from_revision_id = TextLine()

    to_revision_id = TextLine()

    diff = Object(title=_('The Diff object.'), schema=IDiff)

    def destroySelf():
        """Destroy this object."""


class IStaticDiffSource(Interface):
    """Component that can acquire StaticDiffs."""

    def acquire(from_revision_id, to_revision_id, repository):
        """Get or create a StaticDiff."""

    def acquireFromText(from_revision_id, to_revision_id, text):
        """Get or create a StaticDiff from a string.

        If a StaticDiff exists for this revision_id pair, the text is ignored.
        """


class IPreviewDiff(Interface):
    """A diff generated to show actual diff between two branches.

    This diff will be used primarily for branch merge proposals where we are
    trying to determine the effective changes of landing the source branch on
    the target branch.
    """

    source_revision_id = TextLine(
        title=_('The tip revision id of the source branch used to generate '
                'the diff.'))

    target_revision_id = TextLine(
        title=_('The tip revision id of the target branch used to generate '
                'the diff.'))

    dependent_revision_id = TextLine(
        title=_('The tip revision id of the dependent branch used to '
                'generate the diff.'))

    diff = Object(title=_('The Diff object.'), schema=IDiff)

    conflicts = Text(
        title=_('The text describing any path or text conflicts.'))

    stale = Bool(
        readonly=True, description=_(
            'If the preview diff is stale, it is out of date when compared '
            'to the tip revisions of the source, target, and possibly '
            'dependent branches.'))
