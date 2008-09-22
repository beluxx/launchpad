#!/usr/bin/python2.4
# Copyright 2008 Canonical Ltd.  All rights reserved.
# pylint: disable-msg=W0403

"""
Cron job that parses pending HWDB submissions.
"""

import _pythonpath

from canonical.launchpad.scripts.base import LaunchpadCronScript
from canonical.launchpad.scripts.hwdbsubmissions import (
    process_pending_submissions)


class HWDBSubmissionProcessor(LaunchpadCronScript):

    def add_my_options(self):
        """See `LaunchpadScript`."""
        self.parser.add_option(
            '-m', '--max-submissions',
            help='Limit the number of submissions which will be processed.')

    def main(self):
        max_submissions = self.options.max_submissions
        if max_submissions is not None:
            try:
                max_submissions = int(self.options.max_submissions)
            except ValueError:
                self.logger.error(
                    'Invalid value for --max_submissions specified: %r.'
                    % max_submissions)
                return
            if max_submissions <= 0:
                self.logger.error(
                    '--max_submissions must be a positive integer.')
                return

        process_pending_submissions(self.txn, self.logger, max_submissions)

if __name__ == '__main__':
    script = HWDBSubmissionProcessor(
        'hwdbsubmissions', dbuser='hwdb-submission-processor')
    script.lock_and_run()
