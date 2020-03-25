# Copyright 2009-2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database classes including and related to CodeImport."""

__metaclass__ = type

__all__ = [
    'CodeImport',
    'CodeImportSet',
    ]

from datetime import timedelta

from lazr.lifecycle.event import ObjectCreatedEvent
from sqlobject import (
    ForeignKey,
    IntervalCol,
    SQLMultipleJoin,
    SQLObjectNotFound,
    StringCol,
    )
from storm.expr import (
    And,
    Desc,
    Func,
    Select,
    )
from storm.locals import (
    Int,
    Store,
    )
from storm.references import Reference
from zope.component import getUtility
from zope.event import notify
from zope.interface import implementer
from zope.security.proxy import removeSecurityProxy

from lp.app.errors import NotFoundError
from lp.code.enums import (
    BranchType,
    CodeImportJobState,
    CodeImportResultStatus,
    CodeImportReviewStatus,
    GitRepositoryType,
    NON_CVS_RCS_TYPES,
    RevisionControlSystems,
    TargetRevisionControlSystems,
    )
from lp.code.errors import (
    CodeImportAlreadyRequested,
    CodeImportAlreadyRunning,
    CodeImportInvalidTargetType,
    CodeImportNotInReviewedState,
    )
from lp.code.interfaces.branch import IBranch
from lp.code.interfaces.branchtarget import IBranchTarget
from lp.code.interfaces.codeimport import (
    ICodeImport,
    ICodeImportSet,
    )
from lp.code.interfaces.codeimportevent import ICodeImportEventSet
from lp.code.interfaces.codeimportjob import ICodeImportJobWorkflow
from lp.code.interfaces.githosting import IGitHostingClient
from lp.code.interfaces.gitnamespace import get_git_namespace
from lp.code.interfaces.gitrepository import IGitRepository
from lp.code.interfaces.hasgitrepositories import IHasGitRepositories
from lp.code.mail.codeimport import code_import_updated
from lp.code.model.codeimportjob import CodeImportJobWorkflow
from lp.code.model.codeimportresult import CodeImportResult
from lp.registry.interfaces.person import validate_public_person
from lp.services.config import config
from lp.services.database.constants import DEFAULT
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import SQLBase


@implementer(ICodeImport)
class CodeImport(SQLBase):
    """See `ICodeImport`."""
    _table = 'CodeImport'
    _defaultOrder = ['id']

    def __init__(self, target=None, *args, **kwargs):
        if target is not None:
            assert 'branch' not in kwargs
            assert 'repository' not in kwargs
            if IBranch.providedBy(target):
                kwargs['branch'] = target
            elif IGitRepository.providedBy(target):
                kwargs['git_repository'] = target
            else:
                raise AssertionError("Unknown code import target %s" % target)
        super(CodeImport, self).__init__(*args, **kwargs)

    date_created = UtcDateTimeCol(notNull=True, default=DEFAULT)
    branch = ForeignKey(dbName='branch', foreignKey='Branch', notNull=False)
    git_repositoryID = Int(name='git_repository', allow_none=True)
    git_repository = Reference(git_repositoryID, 'GitRepository.id')

    @property
    def target(self):
        if self.branch is not None:
            return self.branch
        else:
            assert self.git_repository is not None
            return self.git_repository

    registrant = ForeignKey(
        dbName='registrant', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    owner = ForeignKey(
        dbName='owner', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    assignee = ForeignKey(
        dbName='assignee', foreignKey='Person',
        storm_validator=validate_public_person, notNull=False, default=None)

    review_status = EnumCol(schema=CodeImportReviewStatus, notNull=True,
        default=CodeImportReviewStatus.REVIEWED)

    rcs_type = EnumCol(schema=RevisionControlSystems,
        notNull=False, default=None)

    @property
    def target_rcs_type(self):
        if self.branch is not None:
            return TargetRevisionControlSystems.BZR
        else:
            return TargetRevisionControlSystems.GIT

    cvs_root = StringCol(default=None)

    cvs_module = StringCol(default=None)

    url = StringCol(default=None)

    date_last_successful = UtcDateTimeCol(default=None)
    update_interval = IntervalCol(default=None)

    @property
    def effective_update_interval(self):
        """See `ICodeImport`."""
        if self.update_interval is not None:
            return self.update_interval
        default_interval_dict = {
            RevisionControlSystems.CVS:
                config.codeimport.default_interval_cvs,
            RevisionControlSystems.BZR_SVN:
                config.codeimport.default_interval_subversion,
            RevisionControlSystems.GIT:
                config.codeimport.default_interval_git,
            RevisionControlSystems.BZR:
                config.codeimport.default_interval_bzr,
            }
        # The default can be removed when HG is fully purged.
        seconds = default_interval_dict.get(self.rcs_type, 21600)
        return timedelta(seconds=seconds)

    import_job = Reference("<primary key>", "CodeImportJob.code_import_id",
                           on_remote=True)

    def getImportDetailsForDisplay(self):
        """See `ICodeImport`."""
        assert self.rcs_type is not None, (
            "Only makes sense for series with import details set.")
        if self.rcs_type == RevisionControlSystems.CVS:
            return '%s %s' % (self.cvs_root, self.cvs_module)
        elif self.rcs_type in (
            RevisionControlSystems.SVN,
            RevisionControlSystems.GIT,
            RevisionControlSystems.BZR_SVN,
            RevisionControlSystems.HG,
            RevisionControlSystems.BZR):
            return self.url
        else:
            raise AssertionError(
                "Unknown rcs type: %s" % self.rcs_type.title)

    def _removeJob(self):
        """If there is a pending job, remove it."""
        job = self.import_job
        if job is not None:
            if job.state == CodeImportJobState.PENDING:
                CodeImportJobWorkflow().deletePendingJob(self)

    results = SQLMultipleJoin(
        'CodeImportResult', joinColumn='code_import',
        orderBy=['-date_job_started'])

    @property
    def consecutive_failure_count(self):
        """See `ICodeImport`."""
        # This SQL translates as "how many code import results have there been
        # for this code import since the last successful one".
        # This is not very efficient for long lists of code imports.
        last_success = Func(
            "coalesce",
            Select(
                CodeImportResult.id,
                And(CodeImportResult.status.is_in(
                        CodeImportResultStatus.successes),
                    CodeImportResult.code_import == self),
                order_by=Desc(CodeImportResult.id),
                limit=1),
            0)
        return Store.of(self).find(
            CodeImportResult,
            CodeImportResult.code_import == self,
            CodeImportResult.id > last_success).count()

    def updateFromData(self, data, user):
        """See `ICodeImport`."""
        event_set = getUtility(ICodeImportEventSet)
        new_whiteboard = None
        if 'whiteboard' in data:
            whiteboard = data.pop('whiteboard')
            # XXX cjwatson 2016-10-03: Do we need something similar for Git?
            if self.branch is not None:
                if whiteboard != self.branch.whiteboard:
                    if whiteboard is None:
                        new_whiteboard = ''
                    else:
                        new_whiteboard = whiteboard
                    self.branch.whiteboard = whiteboard
        token = event_set.beginModify(self)
        for name, value in data.items():
            setattr(self, name, value)
        if 'review_status' in data:
            if data['review_status'] == CodeImportReviewStatus.REVIEWED:
                if self.import_job is None:
                    CodeImportJobWorkflow().newJob(self)
            else:
                self._removeJob()
        event = event_set.newModify(self, user, token)
        if event is not None or new_whiteboard is not None:
            code_import_updated(self, event, new_whiteboard, user)
        return event

    def __repr__(self):
        return "<CodeImport for %s>" % self.target.unique_name

    def tryFailingImportAgain(self, user):
        """See `ICodeImport`."""
        if self.review_status != CodeImportReviewStatus.FAILING:
            raise AssertionError(
                "review_status is %s not FAILING" % self.review_status.name)
        self.updateFromData(
            {'review_status': CodeImportReviewStatus.REVIEWED}, user)
        getUtility(ICodeImportJobWorkflow).requestJob(self.import_job, user)

    def requestImport(self, requester, error_if_already_requested=False):
        """See `ICodeImport`."""
        if self.import_job is None:
            # Not in automatic mode.
            raise CodeImportNotInReviewedState(
                "This code import is %s, and must be Reviewed for you to "
                "call requestImport."
                % self.review_status.name)
        if self.import_job.state != CodeImportJobState.PENDING:
            assert self.import_job.state == CodeImportJobState.RUNNING
            raise CodeImportAlreadyRunning(
                "This code import is already running.")
        elif self.import_job.requesting_user is not None:
            if error_if_already_requested:
                raise CodeImportAlreadyRequested("This code import has "
                    "already been requested to run.",
                    self.import_job.requesting_user)
        else:
            getUtility(ICodeImportJobWorkflow).requestJob(
                self.import_job, requester)


@implementer(ICodeImportSet)
class CodeImportSet:
    """See `ICodeImportSet`."""

    def new(self, registrant, context, branch_name, rcs_type, target_rcs_type,
            url=None, cvs_root=None, cvs_module=None, review_status=None,
            owner=None):
        """See `ICodeImportSet`."""
        if rcs_type == RevisionControlSystems.CVS:
            assert cvs_root is not None and cvs_module is not None
            assert url is None
        elif rcs_type in NON_CVS_RCS_TYPES:
            assert cvs_root is None and cvs_module is None
            assert url is not None
        else:
            raise AssertionError(
                "Don't know how to sanity check source details for unknown "
                "rcs_type %s" % rcs_type)
        if owner is None:
            owner = registrant
        if target_rcs_type == TargetRevisionControlSystems.BZR:
            # XXX cjwatson 2016-10-15: Testing
            # IHasBranches.providedBy(context) would seem more in line with
            # the Git case, but for some reason ProductSeries doesn't
            # provide that.  We should sync this up somehow.
            try:
                target = IBranchTarget(context)
            except TypeError:
                raise CodeImportInvalidTargetType(context, target_rcs_type)
            namespace = target.getNamespace(owner)
        elif target_rcs_type == TargetRevisionControlSystems.GIT:
            if not IHasGitRepositories.providedBy(context):
                raise CodeImportInvalidTargetType(context, target_rcs_type)
            if rcs_type != RevisionControlSystems.GIT:
                raise AssertionError(
                    "Can't import rcs_type %s into a Git repository" %
                    rcs_type)
            target = namespace = get_git_namespace(context, owner)
        else:
            raise AssertionError(
                "Can't import to target_rcs_type %s" % target_rcs_type)
        if review_status is None:
            # Auto approve imports.
            review_status = CodeImportReviewStatus.REVIEWED
        if not target.supports_code_imports:
            raise AssertionError("%r doesn't support code imports" % target)
        # Create the branch for the CodeImport.
        if target_rcs_type == TargetRevisionControlSystems.BZR:
            import_target = namespace.createBranch(
                branch_type=BranchType.IMPORTED, name=branch_name,
                registrant=registrant)
        else:
            import_target = namespace.createRepository(
                repository_type=GitRepositoryType.IMPORTED, name=branch_name,
                registrant=registrant)
            hosting_path = import_target.getInternalPath()
            getUtility(IGitHostingClient).create(hosting_path)

        code_import = CodeImport(
            registrant=registrant, owner=owner, target=import_target,
            rcs_type=rcs_type, url=url,
            cvs_root=cvs_root, cvs_module=cvs_module,
            review_status=review_status)

        getUtility(ICodeImportEventSet).newCreate(code_import, registrant)
        notify(ObjectCreatedEvent(code_import))

        # If created in the reviewed state, create a job.
        if review_status == CodeImportReviewStatus.REVIEWED:
            CodeImportJobWorkflow().newJob(code_import)

        return code_import

    def delete(self, code_import):
        """See `ICodeImportSet`."""
        if code_import.import_job is not None:
            removeSecurityProxy(code_import.import_job).destroySelf()
        CodeImport.delete(code_import.id)

    def get(self, id):
        """See `ICodeImportSet`."""
        try:
            return CodeImport.get(id)
        except SQLObjectNotFound:
            raise NotFoundError(id)

    def getByCVSDetails(self, cvs_root, cvs_module):
        """See `ICodeImportSet`."""
        return CodeImport.selectOneBy(
            cvs_root=cvs_root, cvs_module=cvs_module)

    def getByURL(self, url, target_rcs_type):
        """See `ICodeImportSet`."""
        clauses = [CodeImport.url == url]
        if target_rcs_type == TargetRevisionControlSystems.BZR:
            clauses.append(CodeImport.branch != None)
        elif target_rcs_type == TargetRevisionControlSystems.GIT:
            clauses.append(CodeImport.git_repository != None)
        else:
            raise AssertionError(
                "Unknown target_rcs_type %s" % target_rcs_type)
        return IStore(CodeImport).find(CodeImport, *clauses).one()

    def getByBranch(self, branch):
        """See `ICodeImportSet`."""
        return CodeImport.selectOneBy(branch=branch)

    def getByGitRepository(self, repository):
        return CodeImport.selectOneBy(git_repository=repository)

    def search(self, review_status=None, rcs_type=None, target_rcs_type=None):
        """See `ICodeImportSet`."""
        clauses = []
        if review_status is not None:
            clauses.append(CodeImport.review_status == review_status)
        if rcs_type is not None:
            clauses.append(CodeImport.rcs_type == rcs_type)
        if target_rcs_type == TargetRevisionControlSystems.BZR:
            clauses.append(CodeImport.branch != None)
        elif target_rcs_type == TargetRevisionControlSystems.GIT:
            clauses.append(CodeImport.git_repository != None)
        return IStore(CodeImport).find(CodeImport, *clauses)
