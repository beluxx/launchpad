#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# pylint: disable-msg=W0403
"""Unembargo a package from the security private PPA."""

import _pythonpath

from lp.services.config import config
from lp.soyuz.scripts.packagecopier import UnembargoSecurityPackage


if __name__ == '__main__':
    script = UnembargoSecurityPackage(
        'unembargo-package', dbuser=config.archivepublisher.dbuser)
    script.lock_and_run()

