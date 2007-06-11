# Copyright 2007 Canonical Ltd.  All rights reserved.

import os
import re
import errno
import shutil
import subprocess

HERE = os.path.dirname(__file__)


def monkey_patch(mailman_path, config):
    """Monkey-patch an installed Mailman 2.1 tree.

    Rather than maintain a forked tree of Mailman 2.1, we apply a set of
    changes to an installed Mailman tree.  This tree can be found rooted at
    mailman_path.

    This should usually mean just copying a file from this directory into
    mailman_path.  Rather than build a lot of process into the mix, just hard
    code each transformation here.
    """
    # Hook Mailman to Launchpad by writing a custom mm_cfg.py file which adds
    # the top of our Launchpad tree to Mailman's sys.path.  The mm_cfg.py file
    # won't do much more than set up sys.path and do an from-import-* to get
    # everything that doesn't need to be dynamically calculated at run-time.
    # Things that can only be calculated at run-time are written to mm_cfg.py
    # now.  It's okay to simply overwrite any existing mm_cfg.py, since we'll
    # provide everything Mailman needs.
    #
    # Remember, don't rely on Launchpad's config object in the mm_cfg.py file
    # or in the canonical.mailman.monkeypatches.defaults module because
    # Mailman will not be able to initialize Launchpad's configuration system.
    # Instead, anything that's needed from config should be written to the
    # mm_cfg.py file now.
    #
    # Calculate the parent directory of the canonical package.  This directory
    # will get appended to Mailman's sys.path.
    import canonical
    launchpad_top = os.path.dirname(os.path.dirname(canonical.__file__))
    # Write the mm_cfg.py file, filling in the dynamic values now.
    host, port = config.mailman.smtp
    config_path = os.path.join(mailman_path, 'Mailman', 'mm_cfg.py')
    config_file = open(config_path, 'w')
    try:
        print >> config_file, """\
# Automatically generated by runlaunchpad.py

# Set up Mailman's sys.path to pick up the top of Launchpad's tree
import sys
sys.path.insert(0, '%(launchpad_top)s')

# Pick up Launchpad static overrides.  This will also pick up the standard
# Mailman.Defaults.* variables.
from canonical.launchpad.mailman.monkeypatches.defaults import *

# Our dynamic overrides of all the static defaults.
SMTPHOST = '%(smtp_host)s'
SMTPPORT = %(smtp_port)d
""" % dict(launchpad_top=launchpad_top,
           smtp_host=host,
           smtp_port=port,
           )
    finally:
        config_file.close()
