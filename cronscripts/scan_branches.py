#!/usr/bin/python -S
#
# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Scan branches for new revisions."""

__metaclass__ = type

import _pythonpath

import resource

from lp.services.job.runner import JobCronScript
from lp.code.interfaces.branchjob import IBranchScanJobSource


class RunScanBranches(JobCronScript):
    """Run BranchScanJob jobs."""

    config_name = 'branchscanner'
    source_interface = IBranchScanJobSource


if __name__ == '__main__':

    resource.setrlimit(resource.RLIMIT_AS, (2L << 30, 2L << 30))

    script = RunScanBranches()
    script.lock_and_run()
