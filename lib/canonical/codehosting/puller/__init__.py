# Copyright 2006-2007 Canonical Ltd.  All rights reserved.

__metaclass__ = type
__all__ = ['configure_oops_reporting', 'get_lock_id_for_branch_id', 'mirror']


import datetime

import pytz

from twisted.internet import defer


def get_lock_id_for_branch_id(branch_id):
    """Return the lock id that should be used for a branch with the passed id.
    """
    return 'worker-for-branch-%s@supermirror'%(branch_id,)


from canonical.codehosting.puller.scheduler import LockError
from canonical.config import config
from canonical.launchpad.interfaces import BranchType


UTC = pytz.timezone('UTC')


def configure_oops_reporting(branch_type):
    """Set up OOPS reporting for this scripts.

    :param branch_type: The type of branch that is being mirrored.
    """

    # XXX: JonathanLange 2007-10-04: The config schema uses old-fashioned
    # names for branch types. Map from BranchType objects to the older names.
    branch_type_map = {
        BranchType.HOSTED: 'upload',
        BranchType.MIRRORED: 'mirror',
        BranchType.IMPORTED: 'import'
        }
    old_school_branch_type_name = branch_type_map[branch_type]

    errorreports = getattr(
        config.supermirror,
        '%s_errorreports' % (old_school_branch_type_name,))

    # Customize the oops reporting config.
    config.launchpad.errorreports.oops_prefix = errorreports.oops_prefix
    config.launchpad.errorreports.errordir = errorreports.errordir
    config.launchpad.errorreports.copy_to_zlog = errorreports.copy_to_zlog


def mirror(logger, manager):
    """Mirror all current branches that need to be mirrored."""
    try:
        manager.lock()
    except LockError, exception:
        logger.info('Could not acquire lock: %s', exception)
        return defer.succeed(0)

    date_started = datetime.datetime.now(UTC)

    def recordSuccess(ignored):
        date_completed = datetime.datetime.now(UTC)
        return manager.recordActivity(date_started, date_completed)

    def unlock(passed_through):
        manager.unlock()
        return passed_through

    deferred = manager.run()
    deferred.addCallback(recordSuccess)
    deferred.addBoth(unlock)
    return deferred

