# Copyright 2008 Canonical Ltd.  All rights reserved.

"""XXX."""

__metaclass__ = type
__all__ = [
    'CodeImportDispatcher',
    ]

import os
import socket
import subprocess
import xmlrpclib

from zope.component import getUtility

from canonical.codehosting import get_rocketfuel_root
from canonical.config import config
from canonical.launchpad.interfaces import (
    CodeImportMachineOfflineReason, CodeImportMachineState, ICodeImportJobSet,
    ICodeImportMachineSet)


class CodeImportDispatcher:
    """XXX."""

    worker_script = os.path.join(
        get_rocketfuel_root(), 'scripts', 'code-import-worker-db.py')

    def __init__(self, txn, logger):
        """XXX."""
        self.txn = txn
        self.logger = logger

    def getHostname(self):
        """XXX."""
        if config.codeimportdispatcher.forced_hostname:
            return config.codeimportdispatcher.forced_hostname
        else:
            return socket.gethostname()

    def dispatchJob(self, job_id):
        """XXX."""
        # Just launch the process and forget about it.
        log_file = os.path.join(
            config.codeimportdispatcher.worker_log_dir,
            'code-import-worker-%d.log' % (job_id,))
        subprocess.Popen(
            [self.worker_script, str(job_id), '-vv', '--log-file', log_file])

    def getJobForMachine(self, machine):
        """XXX."""
        server_proxy = xmlrpclib.ServerProxy(
            config.codeimport.codeimportscheduler_url)
        return server_proxy.getJobForMachine(machine.hostname)

    def dispatchJobs(self):
        """XXX."""

        machine = getUtility(ICodeImportMachineSet).getByHostname(
            self.getHostname())

        if machine.state == CodeImportMachineState.OFFLINE:
            self.logger.info(
                "Machine is in OFFLINE state, not looking for jobs.")
            return

        job_set = getUtility(ICodeImportJobSet)
        job_count = job_set.getJobsRunningOnMachine(machine).count()

        if machine.state == CodeImportMachineState.QUIESCING:
            if job_count == 0:
                self.logger.info(
                    "Machine is in QUIESCING state and no jobs running, "
                    "going OFFLINE.")
                machine.setOffline(
                    CodeImportMachineOfflineReason.QUIESCED)
                # This is the only case where we modify the database.
                self.txn.commit()
                return
            self.logger.info(
                "Machine is in QUIESCING state, not looking for jobs.")
            return

        if job_count >= config.codeimportdispatcher.max_jobs_per_machine:
            # There are enough jobs running on this machine already.
            return

        job_id = self.getJobForMachine(machine)

        if job_id == 0:
            # There are no jobs that need to be run.
            self.logger.info(
                "No jobs pending.")
            return

        self.logger.info("Dispatching job %d." % job_id)

        self.dispatchJob(job_id)

