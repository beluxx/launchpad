#!/usr/bin/python2.5
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# pylint: disable-msg=W0403

"""Cron job to update Product.remote_product using bug watch information.  """

import time
import _pythonpath

from canonical.config import config
from lp.services.scripts.base import LaunchpadCronScript
from canonical.launchpad.scripts.updateremoteproduct import (
    RemoteProductUpdater)


class UpdateRemoteProduct(LaunchpadCronScript):

    def main(self):
        start_time = time.time()

        updater = RemoteProductUpdater(self.txn, self.logger)
        updater.update()

        run_time = time.time() - start_time
        self.logger.info("Time for this run: %.3f seconds." % run_time)


if __name__ == '__main__':
    script = UpdateRemoteProduct(
        "updateremoteproduct", dbuser=config.updateremoteproduct.dbuser)
    script.lock_and_run()
