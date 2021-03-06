# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Run the doctests and pagetests.
"""

from __future__ import absolute_import, print_function, unicode_literals

import os

from lp.services.testing import build_test_suite
from lp.testing.layers import LaunchpadZopelessLayer
from lp.testing.pages import setUpGlobs
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


here = os.path.dirname(os.path.realpath(__file__))
special = {
    'language.txt': LayeredDocFileSuite(
        '../doc/language.txt',
        layer=LaunchpadZopelessLayer,
        setUp=lambda test: setUp(test, future=True), tearDown=tearDown),
    }


def test_suite():
    return build_test_suite(
        here, special, setUp=lambda test: setUp(test, future=True),
        pageTestsSetUp=lambda test: setUpGlobs(test, future=True))
