#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# pylint: disable-msg=C0103,W0403
"""Process pending PackageDiffs.

Process a optionally limited set of pending PackageDiffs.

By default it process up to 50 diffs each run, which is enough to catch
up on 1 hour of uploads (on average).

However users might benefit for more frequently runs since the diff ETA
relative to the upload will be shorter.

The cycle time needs to be balanced with the run time to produce the shortest
diff ETA and to not overlap much, for instance, if it has to diff monster
sources like openoffice or firefox.

Experiments with the cycle time will be safe enough and won't sink the host
performance, since the lock file is exclusive.
"""

__metaclass__ = type

import _pythonpath

from lp.services.config import config
from lp.soyuz.scripts.packagediff import ProcessPendingPackageDiffs


if __name__ == '__main__':
    script = ProcessPendingPackageDiffs(
        'process-pending-packagediffs', dbuser=config.uploader.dbuser)
    script.lock_and_run()
