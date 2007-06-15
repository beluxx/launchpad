#!/usr/bin/python2.4
# Copyright 2007 Canonical Ltd.  All rights reserved.
"""It provides easy integration of other scripts without database access.

   It should provide an easy way to retrieve current information from Launchpad
   System when using plain shell scripts, for example:

   * CURRENT distrorelease name: `./ubuntu-helper.py -d ubuntu current`
   * DEVEVELOPMENT distrorelease name: `./ubuntu-helper.py -d ubuntu development`
   * Distorelease architectures:
       `./lp-query-distro.py -d ubuntu -s feisty archs`
   * Distorelease official architectures:
       `./lp-query-distro.py -d ubuntu -s feisty official_archs`
   * Distorelease nominated-arch-indep:
       `./lp-query-distro.py -d ubuntu -s feisty nominated_arch_indep`

   Standard Output will carry the successfully executed information and
   exit_code will be ZERO.
   In case of failure, exit_code will be different than ZERO and Standard Error
   will contain debug information.
   """

import _pythonpath

from canonical.config import config
from canonical.launchpad.scripts.base import (LaunchpadScript,
    LaunchpadScriptFailure)
from canonical.launchpad.scripts.ftpmaster import LpQueryDistro


if __name__ == '__main__':
    # XXX cprov 20070514: we can use read-only DB user for this task,
    # however the mandatory ScriptActivity recording support added in
    # LaunchpadScript by RF-4128 doesn't work if we do that.
    script = LpQueryDistro('lp-query-distro', dbuser='uploader')
    script.run()
