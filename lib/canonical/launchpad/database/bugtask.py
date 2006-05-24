# Copyright 2004-2005 Canonical Ltd.  All rights reserved.

__metaclass__ = type
__all__ = [
    'BugTask',
    'BugTaskSet',
    'bugtask_sort_key']

import urllib
import cgi
import datetime

from sqlobject import (
    ForeignKey, StringCol, SQLMultipleJoin, SQLObjectNotFound)

import pytz

from zope.component import getUtility
from zope.interface import implements
from zope.security.proxy import isinstance as zope_isinstance

from canonical.lp import dbschema
from canonical.database.sqlbase import SQLBase, sqlvalues, quote_like
from canonical.database.constants import UTC_NOW
from canonical.database.datetimecol import UtcDateTimeCol
from canonical.launchpad.searchbuilder import any, NULL
from canonical.launchpad.components.bugtask import BugTaskMixin, mark_task
from canonical.launchpad.interfaces import (
    BugTaskSearchParams, IBugTask, IBugTaskSet, IUpstreamBugTask,
    IDistroBugTask, IDistroReleaseBugTask, NotFoundError,
    ILaunchpadCelebrities, ISourcePackage, IDistributionSourcePackage,
    UNRESOLVED_BUGTASK_STATUSES, RESOLVED_BUGTASK_STATUSES)


debbugsseveritymap = {None:        dbschema.BugTaskImportance.UNTRIAGED,
                      'wishlist':  dbschema.BugTaskImportance.WISHLIST,
                      'minor':     dbschema.BugTaskImportance.LOW,
                      'normal':    dbschema.BugTaskImportance.MEDIUM,
                      'important': dbschema.BugTaskImportance.HIGH,
                      'serious':   dbschema.BugTaskImportance.HIGH,
                      'grave':     dbschema.BugTaskImportance.HIGH,
                      'critical':  dbschema.BugTaskImportance.CRITICAL}

def bugtask_sort_key(bugtask):
    """A sort key for a set of bugtasks. We want:

          - products first
          - distro tasks, followed by their distrorelease tasks
          - ubuntu first among the distros
    """
    if bugtask.product:
        product = bugtask.product.name
    else:
        product = None
    if bugtask.distribution:
        distribution = bugtask.distribution.name
    else:
        distribution = None
    if bugtask.distrorelease:
        distrorelease = bugtask.distrorelease.version
        distribution = bugtask.distrorelease.distribution.name
    else:
        distrorelease = None
    if bugtask.sourcepackagename:
        sourcepackagename = bugtask.sourcepackagename.name
    else:
        sourcepackagename = None
    # and move ubuntu to the top
    if distribution == 'ubuntu':
        distribution = '-'
    return (bugtask.bug, distribution, product, distrorelease,
            sourcepackagename)


class BugTask(SQLBase, BugTaskMixin):
    implements(IBugTask)
    _table = "BugTask"
    _defaultOrder = ['distribution', 'product', 'distrorelease',
                     'milestone', 'sourcepackagename']

    bug = ForeignKey(dbName='bug', foreignKey='Bug', notNull=True)
    product = ForeignKey(
        dbName='product', foreignKey='Product',
        notNull=False, default=None)
    sourcepackagename = ForeignKey(
        dbName='sourcepackagename', foreignKey='SourcePackageName',
        notNull=False, default=None)
    distribution = ForeignKey(
        dbName='distribution', foreignKey='Distribution',
        notNull=False, default=None)
    distrorelease = ForeignKey(
        dbName='distrorelease', foreignKey='DistroRelease',
        notNull=False, default=None)
    milestone = ForeignKey(
        dbName='milestone', foreignKey='Milestone',
        notNull=False, default=None)
    status = dbschema.EnumCol(
        dbName='status', notNull=True,
        schema=dbschema.BugTaskStatus,
        default=dbschema.BugTaskStatus.UNCONFIRMED)
    statusexplanation = StringCol(dbName='statusexplanation', default=None)
    importance = dbschema.EnumCol(
        dbName='importance', notNull=True,
        schema=dbschema.BugTaskImportance,
        default=dbschema.BugTaskImportance.UNTRIAGED)
    assignee = ForeignKey(
        dbName='assignee', foreignKey='Person',
        notNull=False, default=None)
    bugwatch = ForeignKey(dbName='bugwatch', foreignKey='BugWatch',
        notNull=False, default=None)
    date_assigned = UtcDateTimeCol(notNull=False, default=None)
    datecreated  = UtcDateTimeCol(notNull=False, default=UTC_NOW)
    date_confirmed = UtcDateTimeCol(notNull=False, default=None)
    date_inprogress = UtcDateTimeCol(notNull=False, default=None)
    date_closed = UtcDateTimeCol(notNull=False, default=None)
    owner = ForeignKey(foreignKey='Person', dbName='owner', notNull=True)
    # The targetnamecache is a value that is only supposed to be set when a
    # bugtask is created/modified or by the update-bugtask-targetnamecaches
    # cronscript. For this reason it's not exposed in the interface, and
    # client code should always use the targetname read-only property.
    targetnamecache = StringCol(
        dbName='targetnamecache', notNull=False, default=None)

    @property
    def age(self):
        """See canonical.launchpad.interfaces.IBugTask."""
        UTC = pytz.timezone('UTC')
        now = datetime.datetime.now(UTC)

        return now - self.datecreated

    def _init(self, *args, **kw):
        """Marks the task when it's created or fetched from the database."""
        SQLBase._init(self, *args, **kw)
        # We use the forbidden underscore attributes below because, with
        # SQLObject, hitting self.product means querying and
        # instantiating an object; prejoining doesn't help because this
        # happens when the bug task is being instantiated -- too early
        # in cases where we prejoin other things in.
        # XXX: we should use a specific SQLObject API here to avoid the
        # privacy violation.
        #   -- kiko, 2006-03-21
        if self._SO_val_productID is not None:
            mark_task(self, IUpstreamBugTask)
        elif self._SO_val_distroreleaseID is not None:
            mark_task(self, IDistroReleaseBugTask)
        elif self._SO_val_distributionID is not None:
            # If nothing else, this is a distro task.
            mark_task(self, IDistroBugTask)
        else:
            raise AssertionError, "Task %d is floating" % self.id

    @property
    def target_uses_malone(self):
        """See IBugTask"""
        if IUpstreamBugTask.providedBy(self):
            root_target = self.product
        elif IDistroReleaseBugTask.providedBy(self):
            root_target = self.distrorelease.distribution
        elif IDistroBugTask.providedBy(self):
            root_target = self.distribution
        else:
            raise AssertionError, "Task %d is floating" % self.id
        return bool(root_target.official_malone)

    def _SO_setValue(self, name, value, fromPython, toPython):
        # We need to overwrite this method to make sure whenever we change a
        # single attribute of a BugTask the targetnamecache column is updated.
        SQLBase._SO_setValue(self, name, value, fromPython, toPython)
        if name != 'targetnamecache':
            self.updateTargetNameCache()

    def set(self, **kw):
        # We need to overwrite this method to make sure the targetnamecache
        # column is updated when multiple attributes of a bugtask are
        # modified. We can't rely on event subscribers for doing this because
        # they can run in a unpredictable order.
        SQLBase.set(self, **kw)
        # We also can't simply update kw with the value we want for
        # targetnamecache because the _calculate_targetname method needs to
        # access bugtask's attributes that may be available only after
        # SQLBase.set() is called.
        SQLBase.set(self, **{'targetnamecache': self._calculate_targetname()})

    def setImportanceFromDebbugs(self, severity):
        """See canonical.launchpad.interfaces.IBugTask."""
        try:
            self.importance = debbugsseveritymap[severity]
        except KeyError:
            raise ValueError('Unknown debbugs severity "%s"' % severity)
        return self.importance

    def transitionToStatus(self, new_status):
        """See canonical.launchpad.interfaces.IBugTask."""
        if not new_status:
            # This is mainly to facilitate tests which, unlike the
            # normal status form, don't always submit a status when
            # testing the edit form.
            return

        if self.status == new_status:
            # No change in the status, so nothing to do.
            return

        if new_status == dbschema.BugTaskStatus.UNKNOWN:
            # Ensure that all status-related dates are cleared,
            # because it doesn't make sense to have any values set for
            # date_confirmed, date_closed, etc. when the status
            # becomes UNKNOWN.
            self.status = new_status

            self.date_confirmed = None
            self.date_inprogress = None
            self.date_closed = None

            return

        UTC = pytz.timezone('UTC')
        now = datetime.datetime.now(UTC)

        # Record the date of the particular kinds of transitions into
        # certain states.
        if ((self.status.value < dbschema.BugTaskStatus.CONFIRMED.value) and
            (new_status.value >= dbschema.BugTaskStatus.CONFIRMED.value)):
            # Even if the bug task skips the Confirmed status
            # (e.g. goes directly to Fix Committed), we'll record a
            # confirmed date at the same time anyway, otherwise we get
            # a strange gap in our data, and potentially misleading
            # reports.
            self.date_confirmed = now

        if ((self.status.value < dbschema.BugTaskStatus.INPROGRESS.value) and
            (new_status.value >= dbschema.BugTaskStatus.INPROGRESS.value)):
            # Same idea with In Progress as the comment above about
            # Confirmed.
            self.date_inprogress = now

        if ((self.status in UNRESOLVED_BUGTASK_STATUSES) and
            (new_status in RESOLVED_BUGTASK_STATUSES)):
            self.date_closed = now

        # Ensure that we don't have dates recorded for state
        # transitions, if the bugtask has regressed to an earlier
        # workflow state. We want to ensure that, for example, a
        # bugtask that went Unconfirmed => Confirmed => Unconfirmed
        # has a dateconfirmed value of None.
        if new_status in UNRESOLVED_BUGTASK_STATUSES:
            self.date_closed = None

        if new_status < dbschema.BugTaskStatus.CONFIRMED:
            self.date_confirmed = None

        if new_status < dbschema.BugTaskStatus.INPROGRESS:
            self.date_inprogress = None

        self.status = new_status

    def transitionToAssignee(self, assignee):
        """See canonical.launchpad.interfaces.IBugTask."""
        if assignee == self.assignee:
            # No change to the assignee, so nothing to do.
            return

        UTC = pytz.timezone('UTC')
        now = datetime.datetime.now(UTC)
        if self.assignee and not assignee:
            # The assignee is being cleared, so clear the dateassigned
            # value.
            self.date_assigned = None
        if not self.assignee and assignee:
            # The task is going from not having an assignee to having
            # one, so record when this happened
            self.date_assigned = now

        self.assignee = assignee

    def updateTargetNameCache(self):
        """See canonical.launchpad.interfaces.IBugTask."""
        if self.targetnamecache != self._calculate_targetname():
            self.targetnamecache = self._calculate_targetname()

    def asEmailHeaderValue(self):
        """See canonical.launchpad.interfaces.IBugTask."""
        # Calculate an appropriate display value for the assignee.
        if self.assignee:
            if self.assignee.preferredemail:
                assignee_value = self.assignee.preferredemail.email
            else:
                # There is an assignee with no preferredemail, so we'll
                # "degrade" to the assignee.name. This might happen for teams
                # that don't have associated emails or when a bugtask was
                # imported from an external source and had its assignee set
                # automatically, even though the assignee may not even know they
                # have an account in Launchpad. :)
                assignee_value = self.assignee.name
        else:
            assignee_value = 'None'

        # Calculate an appropriate display value for the sourcepackage.
        if self.sourcepackagename:
            sourcepackagename_value = self.sourcepackagename.name
        else:
            # There appears to be no sourcepackagename associated with this
            # task.
            sourcepackagename_value = 'None'

        # Calculate an appropriate display value for the component, if the
        # target looks like some kind of source package.
        component = 'None'
        currentrelease = None
        if ISourcePackage.providedBy(self.target):
            currentrelease = self.target.currentrelease
        if IDistributionSourcePackage.providedBy(self.target):
            if self.target.currentrelease:
                currentrelease = self.target.currentrelease.sourcepackagerelease

        if currentrelease:
            component = currentrelease.component.name

        if IUpstreamBugTask.providedBy(self):
            header_value = 'product=%s;' %  self.target.name
        elif IDistroBugTask.providedBy(self):
            header_value = ((
                'distribution=%(distroname)s; '
                'sourcepackage=%(sourcepackagename)s; '
                'component=%(componentname)s;') %
                {'distroname': self.distribution.name,
                 'sourcepackagename': sourcepackagename_value,
                 'componentname': component})
        elif IDistroReleaseBugTask.providedBy(self):
            header_value = ((
                'distribution=%(distroname)s; '
                'distrorelease=%(distroreleasename)s; '
                'sourcepackage=%(sourcepackagename)s; '
                'component=%(componentname)s;') %
                {'distroname': self.distrorelease.distribution.name,
                 'distroreleasename': self.distrorelease.name,
                 'sourcepackagename': sourcepackagename_value,
                 'componentname': component})

        header_value += ((
            ' status=%(status)s; importance=%(importance)s; '
            'assignee=%(assignee)s;') %
            {'status': self.status.title,
             'importance': self.importance.title,
             'assignee': assignee_value})

        return header_value

    @property
    def statusdisplayhtml(self):
        """See canonical.launchpad.interfaces.IBugTask."""
        assignee = self.assignee
        status = self.status

        if assignee:
            assignee_html = (
                '<img alt="" src="/@@/user.gif" /> '
                '<a href="/people/%s/+assignedbugs">%s</a>' % (
                    urllib.quote_plus(assignee.name),
                    cgi.escape(assignee.browsername)))

            if status in (dbschema.BugTaskStatus.REJECTED,
                          dbschema.BugTaskStatus.FIXCOMMITTED):
                return '%s by %s' % (status.title.lower(), assignee_html)
            else:
                return '%s, assigned to %s' % (status.title.lower(), assignee_html)
        else:
            return status.title.lower() + ' (unassigned)'


class BugTaskSet:

    implements(IBugTaskSet)

    _ORDERBY_COLUMN = {
        "id": "Bug.id",
        "importance": "BugTask.importance",
        "assignee": "BugTask.assignee",
        "targetname": "BugTask.targetnamecache",
        "status": "BugTask.status",
        "title": "Bug.title",
        "milestone": "BugTask.milestone",
        "dateassigned": "BugTask.dateassigned",
        "datecreated": "BugTask.datecreated"}

    title = "A set of bug tasks"

    def get(self, task_id):
        """See canonical.launchpad.interfaces.IBugTaskSet."""
        try:
            bugtask = BugTask.get(task_id)
        except SQLObjectNotFound:
            raise NotFoundError("BugTask with ID %s does not exist" %
                                str(task_id))
        return bugtask

    def search(self, params):
        """See canonical.launchpad.interfaces.IBugTaskSet."""
        assert isinstance(params, BugTaskSearchParams)

        extra_clauses = ['Bug.id = BugTask.bug']
        clauseTables = ['BugTask', 'Bug']

        # These arguments can be processed in a loop without any other
        # special handling.
        standard_args = {
            'bug': params.bug,
            'status': params.status,
            'importance': params.importance,
            'product': params.product,
            'distribution': params.distribution,
            'distrorelease': params.distrorelease,
            'milestone': params.milestone,
            'assignee': params.assignee,
            'sourcepackagename': params.sourcepackagename,
            'owner': params.owner,
        }
        # Loop through the standard, "normal" arguments and build the
        # appropriate SQL WHERE clause. Note that arg_value will be one
        # of:
        #
        # * a searchbuilder.any object, representing a set of acceptable filter
        #   values
        # * a searchbuilder.NULL object
        # * an sqlobject
        # * a dbschema item
        # * None (meaning no filter criteria specified for that arg_name)
        #
        # XXX: is this a good candidate for becoming infrastructure in
        # canonical.database.sqlbase?
        #   -- kiko, 2006-03-16
        for arg_name, arg_value in standard_args.items():
            if arg_value is None:
                continue
            clause = "BugTask.%s " % arg_name
            if zope_isinstance(arg_value, any):
                # When an any() clause is provided, the argument value
                # is a list of acceptable filter values.
                if not arg_value.query_values:
                    continue
                where_arg = ",".join(sqlvalues(*arg_value.query_values))
                clause += "IN (%s)" % where_arg
            elif arg_value is not NULL:
                clause += "= %s" % sqlvalues(arg_value)
            else:
                # The argument value indicates we should match
                # only NULL values for the column named by
                # arg_name.
                clause += "IS NULL"
            extra_clauses.append(clause)

        if params.project:
            clauseTables.append("Product")
            extra_clauses.append("BugTask.product = Product.id")
            if isinstance(params.project, any):
                extra_clauses.append("Product.project IN (%s)" % ",".join(
                    [str(proj.id) for proj in params.project.query_values]))
            elif params.project is NULL:
                extra_clauses.append("Product.project IS NULL")
            else:
                extra_clauses.append("Product.project = %d" %
                                     params.project.id)

        if params.omit_dupes:
            extra_clauses.append("Bug.duplicateof is NULL")

        if params.attachmenttype is not None:
            clauseTables.append('BugAttachment')
            if isinstance(params.attachmenttype, any):
                where_cond = "BugAttachment.type IN (%s)" % ", ".join(
                    sqlvalues(*params.attachmenttype.query_values))
            else:
                where_cond = "BugAttachment.type = %s" % sqlvalues(
                    params.attachmenttype)
            extra_clauses.append("BugAttachment.bug = BugTask.bug")
            extra_clauses.append(where_cond)

        if params.searchtext:
            searchtext_quoted = sqlvalues(params.searchtext)[0]
            searchtext_like_quoted = quote_like(params.searchtext)
            extra_clauses.append(
                "((Bug.fti @@ ftq(%s) OR BugTask.fti @@ ftq(%s)) OR"
                " (BugTask.targetnamecache ILIKE '%%' || %s || '%%'))" % (
                searchtext_quoted, searchtext_quoted, searchtext_like_quoted))

        if params.subscriber is not None:
            clauseTables.append('BugSubscription')
            extra_clauses.append("""Bug.id = BugSubscription.bug AND
                    BugSubscription.person = %(personid)s""" %
                    sqlvalues(personid=params.subscriber.id))

        if params.component:
            clauseTables += ["SourcePackagePublishing", "SourcePackageRelease"]
            distrorelease = None
            if params.distribution:
                distrorelease = params.distribution.currentrelease
            elif params.distrorelease:
                distrorelease = params.distrorelease
            assert distrorelease, (
                "Search by component requires a context with a distribution "
                "or distrorelease")

            if zope_isinstance(params.component, any):
                component_ids = sqlvalues(*params.component.query_values)
            else:
                component_ids = sqlvalues(params.component)

            extra_clauses.extend([
                "BugTask.sourcepackagename = SourcePackageRelease.sourcepackagename",
                "SourcePackageRelease.id = SourcePackagePublishing.sourcepackagerelease",
                "SourcePackagePublishing.distrorelease = %d" % distrorelease.id,
                "SourcePackagePublishing.component IN (%s)" % ', '.join(component_ids),
                "SourcePackagePublishing.status = %s" %
                    dbschema.PackagePublishingStatus.PUBLISHED.value])

        clause = self._getPrivacyFilter(params.user)
        if clause:
            extra_clauses.append(clause)

        orderby = params.orderby
        if orderby is None:
            orderby = []
        elif not zope_isinstance(orderby, (list, tuple)):
            orderby = [orderby]

        # Translate orderby values into corresponding Table.attribute.
        orderby_arg = []
        for orderby_col in orderby:
            if orderby_col.startswith("-"):
                orderby_col = orderby_col[1:]
                orderby_arg.append(
                    "-" + self._ORDERBY_COLUMN[orderby_col])
            else:
                orderby_arg.append(self._ORDERBY_COLUMN[orderby_col])

        # Make sure that the result always is ordered.
        if 'Bug.id' not in orderby_arg and '-Bug.id' not in orderby_arg:
            orderby_arg.append('Bug.id')
        orderby_arg.append('BugTask.id')

        query = " AND ".join(extra_clauses)
        bugtasks = BugTask.select(
            query, prejoinClauseTables=["Bug"], clauseTables=clauseTables,
            prejoins=['sourcepackagename', 'product'],
            orderBy=orderby_arg)

        return bugtasks

    def createTask(self, bug, owner, product=None, distribution=None,
                   distrorelease=None, sourcepackagename=None,
                   status=IBugTask['status'].default,
                   importance=IBugTask['importance'].default,
                   assignee=None, milestone=None):
        """See canonical.launchpad.interfaces.IBugTaskSet."""
        if product:
            assert distribution is None, (
                "Can't pass both distribution and product.")
            # Subscribe product bug and security contacts to all
            # public bugs.
            if not bug.private:
                if product.bugcontact:
                    bug.subscribe(product.bugcontact)
                else:
                    # Make sure that at least someone upstream knows
                    # about this bug. :)
                    bug.subscribe(product.owner)

                if bug.security_related and product.security_contact:
                    bug.subscribe(product.security_contact)
        elif distribution:
            # Subscribe bug and security contacts, if provided, to all
            # public bugs.
            if not bug.private:
                if distribution.bugcontact:
                    bug.subscribe(distribution.bugcontact)
                if bug.security_related and distribution.security_contact:
                    bug.subscribe(distribution.security_contact)

            # Subscribe package bug contacts to public bugs, if package
            # information was provided.
            if sourcepackagename:
                package = distribution.getSourcePackage(sourcepackagename)
                if package.bugcontacts and not bug.private:
                    for pkg_bugcontact in package.bugcontacts:
                        bug.subscribe(pkg_bugcontact.bugcontact)
        else:
            assert distrorelease is not None, 'Got no bugtask target'
            assert distrorelease != distrorelease.distribution.currentrelease, (
                'Bugtasks cannot be opened on the current release.')

        bugtask = BugTask(
            bug=bug,
            product=product,
            distribution=distribution,
            distrorelease=distrorelease,
            sourcepackagename=sourcepackagename,
            status=status,
            importance=importance,
            assignee=assignee,
            owner=owner,
            milestone=milestone)

        return bugtask

    def maintainedBugTasks(self, person, minimportance=None,
                           showclosed=False, orderBy=None, user=None):
        filters = ['BugTask.bug = Bug.id',
                   'BugTask.product = Product.id',
                   'Product.owner = TeamParticipation.team',
                   'TeamParticipation.person = %s' % person.id]

        if not showclosed:
            committed = dbschema.BugTaskStatus.FIXCOMMITTED
            filters.append('BugTask.status < %s' % sqlvalues(committed))

        if minimportance is not None:
            filters.append(
                'BugTask.importance >= %s' % sqlvalues(minimportance))

        privacy_filter = self._getPrivacyFilter(user)
        if privacy_filter:
            filters.append(privacy_filter)

        # We shouldn't show duplicate bug reports.
        filters.append('Bug.duplicateof IS NULL')

        return BugTask.select(" AND ".join(filters),
            clauseTables=['Product', 'TeamParticipation', 'BugTask', 'Bug'])

    def _getPrivacyFilter(self, user):
        """An SQL filter for search results that adds privacy-awareness."""
        if user is None:
            return "Bug.private = FALSE"
        admin_team = getUtility(ILaunchpadCelebrities).admin
        if user.inTeam(admin_team):
            return ""
        # A subselect is used here because joining through
        # TeamParticipation is only relevant to the "user-aware"
        # part of the WHERE condition (i.e. the bit below.) The
        # other half of this condition (see code above) does not
        # use TeamParticipation at all.
        return """
            (Bug.private = FALSE OR Bug.id in (
                 SELECT Bug.id
                 FROM Bug, BugSubscription, TeamParticipation
                 WHERE Bug.id = BugSubscription.bug AND
                       TeamParticipation.person = %(personid)s AND
                       BugSubscription.person = TeamParticipation.team))
                         """ % sqlvalues(personid=user.id)

    def dangerousGetAllTasks(self):
        """DO NOT USE THIS METHOD. For details, see IBugTaskSet"""
        return BugTask.select()

