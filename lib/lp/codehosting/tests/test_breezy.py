# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Launchpad-specific tests of Breezy behaviour."""

from __future__ import absolute_import, print_function

__metaclass__ = type

from lp.testing import TestCase


class TestBreezy(TestCase):
    def test_has_cextensions(self):
        """Ensure Breezy C extensions are being used."""
        try:
            import breezy.bzr._dirstate_helpers_pyx
        except ImportError:
            self.fail("Breezy not built with C extensions.")
