# Copyright 2009-2017 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Launchpad code-hosting system.

NOTE: Importing this package will load any system Bazaar plugins, as well as
all plugins in the bzrplugins/ directory underneath the rocketfuel checkout.
"""

__metaclass__ = type
__all__ = [
    'get_bzr_path',
    'get_BZR_PLUGIN_PATH_for_subprocess',
    ]


import os

import bzrlib
from bzrlib.branch import Branch
from bzrlib.plugin import load_plugins
# This import is needed so that bzr's logger gets registered.
import bzrlib.trace
from zope.security import checker

from lp.services.config import config


def get_bzr_path():
    """Find the path to the copy of Bazaar for this rocketfuel instance"""
    return os.path.join(config.root, 'bin', 'bzr')


def _get_bzr_plugins_path():
    """Find the path to the Bazaar plugins for this rocketfuel instance."""
    return os.path.join(config.root, 'bzrplugins')


def get_BZR_PLUGIN_PATH_for_subprocess():
    """Calculate the appropriate value for the BZR_PLUGIN_PATH environment.

    The '-site' token tells bzrlib not to include the 'site specific plugins
    directory' (which is usually something like
    /usr/lib/pythonX.Y/dist-packages/bzrlib/plugins/) in the plugin search
    path, which would be inappropriate for Launchpad, which may be using a bzr
    egg of an incompatible version.
    """
    return ":".join((_get_bzr_plugins_path(), "-site"))


os.environ['BZR_PLUGIN_PATH'] = get_BZR_PLUGIN_PATH_for_subprocess()

# We want to have full access to Launchpad's Bazaar plugins throughout the
# codehosting package.
load_plugins([_get_bzr_plugins_path()])


def load_bundled_plugin(plugin_name):
    """Load a plugin bundled with Bazaar."""
    from bzrlib.plugin import get_core_plugin_path
    from bzrlib import plugins
    if get_core_plugin_path() not in plugins.__path__:
        plugins.__path__.append(get_core_plugin_path())
    __import__("bzrlib.plugins.%s" % plugin_name)


load_bundled_plugin("weave_fmt")


def dont_wrap_class_and_subclasses(cls):
    checker.BasicTypes.update({cls: checker.NoProxy})
    for subcls in cls.__subclasses__():
        dont_wrap_class_and_subclasses(subcls)


# Don't wrap Branch or its subclasses in Zope security proxies.  Make sure
# the various LoomBranch classes are present first.
import bzrlib.plugins.loom.branch
bzrlib.plugins.loom.branch
dont_wrap_class_and_subclasses(Branch)
