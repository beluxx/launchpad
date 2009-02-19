# Copyright 2004-2005, 2009 Canonical Ltd.  All rights reserved.
__all__ = [
    'RevisionMailJob',
    'BranchJob',
]

from bzrlib.revisionspec import RevisionSpec
from canonical.database.enumcol import EnumCol
from canonical.database.sqlbase import SQLBase
from canonical.lazr.enum import DBEnumeratedType, DBItem
from lazr.delegates import delegates
import simplejson
from sqlobject import ForeignKey, StringCol
from storm.expr import And
import transaction
from zope.component import getUtility
from zope.interface import classProvides, implements

from canonical.launchpad.database.diff import StaticDiff
from canonical.launchpad.database.job import Job
from canonical.launchpad.interfaces.branchjob import (
    IBranchDiffJob, IBranchDiffJobSource, IBranchJob, IRevisionMailJob,
    IRevisionMailJobSource,)
from canonical.launchpad.mailout.branch import BranchMailer
from canonical.launchpad.webapp.interfaces import (
        IStoreSelector, MAIN_STORE, MASTER_FLAVOR)


class BranchJobType(DBEnumeratedType):
    """Values that ICodeImportJob.state can take."""

    STATIC_DIFF = DBItem(0, """
        Static Diff

        This job runs against a branch to produce a diff that cannot change.
        """)

    REVISION_MAIL = DBItem(1, """
        Revision Mail

        This job runs against a branch to send emails about revisions.
        """)


class BranchJob(SQLBase):
    """Base class for jobs related to branches."""

    implements(IBranchJob)

    _table = 'BranchJob'

    job = ForeignKey(foreignKey='Job', notNull=True)

    branch = ForeignKey(foreignKey='Branch', notNull=True)

    job_type = EnumCol(enum=BranchJobType, notNull=True)

    _json_data = StringCol(dbName='json_data')

    @property
    def metadata(self):
        return simplejson.loads(self._json_data)

    def __init__(self, branch, job_type, metadata):
        """Constructor.

        :param branch: The database branch this job relates to.
        :param job_type: The BranchJobType of this job.
        :param metadata: The type-specific variables, as a JSON-compatible
            dict.
        """
        json_data = simplejson.dumps(metadata)
        SQLBase.__init__(
            self, job=Job(), branch=branch, job_type=job_type,
            _json_data=json_data)

    def destroySelf(self):
        """See `IBranchJob`."""
        SQLBase.destroySelf(self)
        self.job.destroySelf()


class BranchDiffJob(object):
    """A Job that calculates the a diff related to a Branch."""

    implements(IBranchDiffJob)

    classProvides(IBranchDiffJobSource)

    delegates(IBranchJob)

    def __init__(self, branch_job):
        self.context = branch_job

    @classmethod
    def create(klass, branch, from_revision_spec, to_revision_spec):
        """See `IBranchDiffJobSource`."""
        metadata = klass.getMetadata(from_revision_spec, to_revision_spec)
        branch_job = BranchJob(branch, BranchJobType.STATIC_DIFF, metadata)
        return klass(branch_job)

    @staticmethod
    def getMetadata(from_revision_spec, to_revision_spec):
        return {
            'from_revision_spec': from_revision_spec,
            'to_revision_spec': to_revision_spec,
        }

    @property
    def from_revision_spec(self):
        return self.metadata['from_revision_spec']

    @property
    def to_revision_spec(self):
        return self.metadata['to_revision_spec']

    def _get_revision_id(self, bzr_branch, spec_string):
        spec = RevisionSpec.from_string(spec_string)
        return spec.as_revision_id(bzr_branch)

    def run(self):
        """See IBranchDiffJob."""
        bzr_branch = self.branch.getBzrBranch()
        from_revision_id = self._get_revision_id(
            bzr_branch, self.from_revision_spec)
        to_revision_id = self._get_revision_id(
            bzr_branch, self.to_revision_spec)
        static_diff = StaticDiff.acquire(
            from_revision_id, to_revision_id, bzr_branch.repository)
        return static_diff


class RevisionMailJob(BranchDiffJob):
    """A Job that calculates the a diff related to a Branch."""

    implements(IRevisionMailJob)

    classProvides(IRevisionMailJobSource)

    def __eq__(self, other):
        return (self.context == other.context)

    def __ne__(self, other):
        return not (self == other)

    @classmethod
    def create(
        klass, branch, revno, from_address, body, perform_diff, subject):
        """See `IRevisionMailJobSource`."""
        metadata = {
            'revno': revno,
            'from_address': from_address,
            'body': body,
            'perform_diff': perform_diff,
            'subject': subject,
        }
        if isinstance(revno, int) and revno > 0:
            from_revision_spec = str(revno - 1)
            to_revision_spec = str(revno)
        else:
            from_revision_spec = None
            to_revision_spec = None
        metadata.update(BranchDiffJob.getMetadata(from_revision_spec,
                        to_revision_spec))
        branch_job = BranchJob(branch, BranchJobType.REVISION_MAIL, metadata)
        return klass(branch_job)

    @staticmethod
    def iterReady():
        """See `IRevisionMailJobSource`."""
        store = getUtility(IStoreSelector).get(MAIN_STORE, MASTER_FLAVOR)
        jobs = store.find(
            (BranchJob),
            And(BranchJob.job_type == BranchJobType.REVISION_MAIL,
                BranchJob.job == Job.id,
                Job.id.is_in(Job.ready_jobs)))
        return (RevisionMailJob(job) for job in jobs)

    @property
    def revno(self):
        revno = self.metadata['revno']
        if isinstance(revno, int):
            revno = long(revno)
        return revno

    @property
    def from_address(self):
        return str(self.metadata['from_address'])

    @property
    def perform_diff(self):
        return self.metadata['perform_diff']

    @property
    def body(self):
        return self.metadata['body']

    @property
    def subject(self):
        return self.metadata['subject']

    def getMailer(self):
        """Return a BranchMailer for this job."""
        if self.perform_diff and self.to_revision_spec is not None:
            diff = BranchDiffJob.run(self)
            transaction.commit()
            diff_text = diff.diff.text
        else:
            diff_text = None
        return BranchMailer.forRevision(
            self.branch, self.revno, self.from_address, self.body,
            diff_text, self.subject)

    def run(self):
        """See `IRevisionMailJob`."""
        self.getMailer().sendAll()


class RevisionsAddedJob(BranchJob):

    @classmethod
    def create(klass, branch, last_scanned_id, last_revision_id):
        metadata = {'last_scanned_id': last_revision_id}

    @staticmethod
    def iter_revision_revno(bzr_branch, branch_revisions):
        for branch_revisions_chunk in iter_list_chunks(
            list(branch_revisions), 1000):
            revision_ids = [branch_revision.revision.revision_id
                for branch_revision in branch_revisions_chunk]
            revisions = bzr_branch.repository.get_revisions(revision_ids)
            for revision, branch_revision in zip(
                revisions, branch_revisions_chunk):
                yield revision, branch_revision.sequence

    def run()
        diff_levels = (BranchSubscriptionNotificationLevel.DIFFSONLY,
                       BranchSubscriptionNotificationLevel.FULL)
        subscriptions = self.db_branch.getSubscriptionsByLevel(diff_levels)
        if len(subscriptions) == 0:
            return
        for subscription in subscriptions:
            if (subscription.max_diff_lines !=
                BranchSubscriptionDiffSize.NODIFF):
                generate_diffs = True
                break
        else:
            generate_diffs = False

        bzr_branch = self.branch.getBzrBranch()
        bzr_branch.lock_read()
        try:
            graph = bzr_branch.repository.get_graph()
            added_revisions = graph.find_difference
                (last_scanned_id, last_revision_id)[1]
            branch_revisions = self.branch.getMainlineBranchRevisions(
                added_revisions)
            for revision, revno in self.iter_revision_revno(branch_revisions):
                assert revno is not None
                mailer = self.getMailerForRevision(
                    bzr_branch, revision, revno, generate_diffs)
                mailer.sendAll()
        finally:
            bzr_branch.unlock()

    def getMailerForRevision(self, bzr_branch, revision, revno,
                             generate_diffs):
        message = get_revision_message(bzr_branch, revision, revno)
        # Use the first (non blank) line of the commit message
        # as part of the subject, limiting it to 100 characters
        # if it is longer.
        message_lines = [
            line.strip() for line in bzr_revision.message.split('\n')
            if len(line.strip()) > 0]
        if len(message_lines) == 0:
            first_line = 'no commit message given'
        else:
            first_line = message_lines[0]
            if len(first_line) > SUBJECT_COMMIT_MESSAGE_LENGTH:
                offset = SUBJECT_COMMIT_MESSAGE_LENGTH - 3
                first_line = first_line[:offset] + '...'
        subject = '[Branch %s] Rev %s: %s' % (
            self.db_branch.unique_name, revno, first_line)
        if generate_diffs:
            if revision.parent_ids > 0:
                parent_id = revision.parents_ids[0]
            else:
                parent_id = NULL_REVISION
            diff = StaticDiff.acquire(parent_id, revision.revision_id,
                                      bzr_branch.repository)
            transaction.commit()
            diff_text = diff.diff.text
        else:
            diff_text = None
        return BranchMailer.forRevision(
            self.branch, revno, self.from_address, message, diff_text,
            subject)


def get_revision_message(bzr_branch, bzr_revision, revno):
    """Return the log message for `bzr_revision` on `bzr_branch`.

    :param bzr_branch: A `bzrlib.branch.Branch` object.
    :param bzr_revision: A Bazaar `Revision` object.
    :return: The commit message entered for `bzr_revision`.
    """
    outf = StringIO()
    lf = log_formatter('long', to_file=outf)
    rev_id = bzr_revision.revision_id
    show_log(bzr_branch,
             lf,
             start_revision=revno,
             end_revision=revno,
             verbose=True)
    return outf.getvalue()
