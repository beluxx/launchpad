# Copyright 2007 Canonical Ltd.  All rights reserved.

"""BranchRevision interfaces."""

__metaclass__ = type
__all__ = ['IBranchRevision', 'IBranchRevisionSet']

from zope.interface import Interface, Attribute
from zope.schema import Int

from canonical.launchpad import _


class IBranchRevision(Interface):
    """The association between a revision and a branch.

    BranchRevision records the relation of all revisions that are part of the
    ancestry of a branch. History revisions have an integer sequence, merged
    revisions have sequence set to None.
    """

    id = Int(title=_('The database revision ID'))

    sequence = Int(
        title=_("Revision number"), required=True,
        description=_("The index of the revision within the branch's history."
            " None for merged revisions which are not part of the history."))
    branch = Attribute("The branch this revision is included in.")
    revision = Attribute("A revision that is included in the branch.")


class IBranchRevisionSet(Interface):
    """The set of all branch-revision associations."""

    def new(branch, sequence, revision):
        """Create a new BranchRevision for the specified branch."""

    def delete(branch_revision_id):
        """Delete the BranchRevision."""

    # NOMERGE: remove that from the interface, we do not want non-test code
    # to use it ever! Move the docstring into the content class.
    def getAncestryForBranch(branch):
        """Returns an unordered list of all BranchRevisions for a branch."""

    def getRevisionHistoryForBranch(branch, limit=None):
        """Returns an ordered list of at most limit BranchRevisions.

        If limit is omitted, then all the BranchRevisions for the branch
        are returned.

        They are ordered with the most recent revision first, and the list
        only contains those in the "leftmost tree", or in other words
        the revisions that match the revision history from bzrlib for this
        branch.
        """
