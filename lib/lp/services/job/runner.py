# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Facilities for running Jobs."""


__metaclass__ = type


__all__ = ['JobRunner']


import sys

import transaction

from lp.services.job.interfaces.job import LeaseHeld, IRunnableJob
from lp.services.mail.sendmail import MailController
from canonical.launchpad.webapp import errorlog


class BaseRunnableJob:
    """Base class for jobs to be run via JobRunner.

    Derived classes should implement IRunnableJob, which requires implementing
    IRunnableJob.run.  They should have a `job` member which implements IJob.

    Subclasses may provide getOopsRecipients, to send mail about oopses.
    If so, they should also provide getOperationDescription.
    """

    def acquireLease(self, duration=300):
        """See `IRunnableJob`."""
        self.job.acquireLease(duration)

    def start(self):
        """See `IRunnableJob`."""
        self.job.start()

    def fail(self):
        """See `IRunnableJob`."""
        self.job.fail()

    def complete(self):
        """See `IRunnableJob`."""
        self.job.complete()

    def queue(self):
        """See `IRunnableJob`."""
        self.job.queue()

    def getOopsRecipients(self):
        """Return a list of email-ids to notify about oopses."""
        return []

    def getOopsMailController(self, oops_id):
        """Return a MailController for notifying people about oopses.

        Return None if there is no-one to notify.
        """
        recipients = self.getOopsRecipients()
        if len(recipients) == 0:
            return None
        body = (
            'Launchpad encountered an internal error during the following'
            ' operation: %s.  It was logged with id %s.  Sorry for the'
            ' inconvenience.' % (self.getOperationDescription(), oops_id))
        return MailController('noreply@launchpad.net', recipients,
                              'NullJob failed.', body)

    def notifyOops(self, oops):
        """Report this oops."""
        ctrl = self.getOopsMailController(oops.id)
        if ctrl is None:
            return
        ctrl.send()


class JobRunner(object):
    """Runner of Jobs."""

    def __init__(self, jobs):
        self.jobs = jobs
        self.completed_jobs = []
        self.incomplete_jobs = []

    @classmethod
    def fromReady(klass, job_class):
        """Return a job runner for all ready jobs of a given class."""
        return klass(job_class.iterReady())

    def runJob(self, job):
        """Attempt to run a job, updating its status as appropriate."""
        job = IRunnableJob(job)
        job.acquireLease()
        # Commit transaction to clear the row lock.
        transaction.commit()
        try:
            job.start()
            transaction.commit()
            job.run()
        except Exception:
            # Commit transaction to update the DB time.
            transaction.commit()
            job.fail()
            self.incomplete_jobs.append(job)
            raise
        else:
            # Commit transaction to update the DB time.
            transaction.commit()
            job.complete()
            self.completed_jobs.append(job)
        # Commit transaction to update job status.
        transaction.commit()

    def runAll(self):
        """Run all the Jobs for this JobRunner."""
        for job in self.jobs:
            try:
                self.runJob(job)
            except LeaseHeld:
                self.incomplete_jobs.append(job)
            except Exception:
                info = sys.exc_info()
                errorlog.globalErrorUtility.raising(info)
                oops = errorlog.globalErrorUtility.getLastOopsReport()
                job.notifyOops(oops)
