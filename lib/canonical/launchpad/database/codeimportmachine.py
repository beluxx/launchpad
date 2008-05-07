# Copyright 2007 Canonical Ltd.  All rights reserved.
# pylint: disable-msg=E0611,W0212

"""Database classes including and related to CodeImportMachine."""

__metaclass__ = type

__all__ = [
    'CodeImportMachine',
    'CodeImportMachineSet',
    ]

from sqlobject import SQLMultipleJoin, StringCol

from zope.component import getUtility
from zope.interface import implements

from canonical.config import config
from canonical.database.constants import DEFAULT
from canonical.database.datetimecol import UtcDateTimeCol
from canonical.database.enumcol import EnumCol
from canonical.database.sqlbase import SQLBase
from canonical.launchpad.interfaces import (
    CodeImportMachineOfflineReason, CodeImportMachineState,
    ICodeImportEventSet, ICodeImportMachine, ICodeImportMachinePublic,
    ICodeImportMachineSet)


class CodeImportMachine(SQLBase):
    """See `ICodeImportMachine`."""

    _defaultOrder = ['hostname']

    implements(ICodeImportMachine, ICodeImportMachinePublic)

    date_created = UtcDateTimeCol(notNull=True, default=DEFAULT)

    hostname = StringCol(default=None)
    state = EnumCol(enum=CodeImportMachineState, notNull=True,
        default=CodeImportMachineState.OFFLINE)
    heartbeat = UtcDateTimeCol(notNull=False)

    current_jobs = SQLMultipleJoin(
        'CodeImportJob', joinColumn='machine', orderBy='date_started')

    def shouldLookForJob(self):
        """See `ICodeImportMachinePublic`."""
        job_count = self.current_jobs.count()

        if self.state == CodeImportMachineState.OFFLINE:
            return False
        elif self.state == CodeImportMachineState.QUIESCING:
            if job_count == 0:
                self.setOffline(
                    CodeImportMachineOfflineReason.QUIESCED)
            return False
        elif self.state == CodeImportMachineState.ONLINE:
            max_jobs = config.codeimportdispatcher.max_jobs_per_machine
            return job_count < max_jobs
        else:
            raise AssertionError(
                "Unknown machine state %r??" % self.state)

    def setOnline(self):
        """See `ICodeImportMachine`."""
        if self.state != CodeImportMachineState.OFFLINE:
            raise AssertionError(
                "State of machine %s was %s."
                % (self.hostname, self.state.name))
        self.state = CodeImportMachineState.ONLINE
        getUtility(ICodeImportEventSet).newOnline(self)

    def setOffline(self, reason):
        """See `ICodeImportMachine`."""
        if self.state not in (CodeImportMachineState.ONLINE,
                              CodeImportMachineState.QUIESCING):
            raise AssertionError(
                "State of machine %s was %s."
                % (self.hostname, self.state.name))
        self.state = CodeImportMachineState.OFFLINE
        getUtility(ICodeImportEventSet).newOffline(self, reason)

    def setQuiescing(self, user, message):
        """See `ICodeImportMachine`."""
        if self.state != CodeImportMachineState.ONLINE:
            raise AssertionError(
                "State of machine %s was %s."
                % (self.hostname, self.state.name))
        self.state = CodeImportMachineState.QUIESCING
        getUtility(ICodeImportEventSet).newQuiesce(self, user, message)


class CodeImportMachineSet(object):
    """See `ICodeImportMachineSet`."""

    implements(ICodeImportMachineSet)

    def getAll(self):
        """See `ICodeImportMachineSet`."""
        return CodeImportMachine.select()

    def getByHostname(self, hostname):
        """See `ICodeImportMachineSet`."""
        return CodeImportMachine.selectOneBy(hostname=hostname)

    def new(self, hostname, state=CodeImportMachineState.OFFLINE):
        """See `ICodeImportMachineSet`."""
        return CodeImportMachine(
            hostname=hostname, heartbeat=None, state=state)
