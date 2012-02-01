# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'find_lp_scripts',
    ]


import os
import subprocess

import canonical
from lp.services.config import config


LP_TREE = os.path.dirname(
    os.path.dirname(os.path.dirname(canonical.__file__)))


SCRIPT_LOCATIONS = [
    'cronscripts',
    'scripts',
    ]


KNOWN_BROKEN = [
    # Needs mysqldb module
    'scripts/migrate-bugzilla-initialcontacts.py',
    'scripts/rosetta/gettext_check_messages.py',
    # sqlobject.DatbaseIndex ?
    'scripts/linkreport.py',
    # Python executable without '.py' extension.
    'scripts/list-team-members',
    'scripts/queue',
    # Bad script, no help.
    'scripts/librarian-report.py',
    'scripts/get-stacked-on-branches.py',
    'scripts/start-loggerhead.py',
    'scripts/stop-loggerhead.py',
    ]


def is_broken(script_path):
    for broken_path in KNOWN_BROKEN:
        if script_path.endswith(broken_path):
            return True
    return False


def find_lp_scripts():
    """Find all scripts/ and cronscripts/ files in the current tree.

    Skips filename starting with '_' or not ending with '.py' or
    listed in the KNOWN_BROKEN blacklist.
    """
    scripts = []
    for script_location in SCRIPT_LOCATIONS:
        location = os.path.join(LP_TREE, script_location)
        for path, dirs, filenames in os.walk(location):
            for filename in filenames:
                script_path = os.path.join(path, filename)
                if (filename.startswith('_') or
                    not filename.endswith('.py') or
                    is_broken(script_path)):
                    continue
                scripts.append(script_path)
    return sorted(scripts)


def run_script(script_relpath, args, expect_returncode=0):
    """Run a script for testing purposes.

    :param script_relpath: The relative path to the script, from the tree
        root.
    :param args: Arguments to provide to the script.
    :param expect_returncode: The return code expected.  If a different value
        is returned, and exception will be raised.
    """
    script = os.path.join(config.root, script_relpath)
    args = [script] + args
    process = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode != expect_returncode:
        raise AssertionError('Failed:\n%s\n%s' % (stdout, stderr))
    return (process.returncode, stdout, stderr)
