# Copyright 2010-2018 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Run the doctests and pagetests.
"""

import os

from lp.services.features.testing import FeatureFixture
from lp.services.testing import build_test_suite
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.pages import (
    PageTestSuite,
    setUpGlobs,
    )
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setGlobs,
    setUp,
    tearDown,
    )


here = os.path.dirname(os.path.realpath(__file__))
bing_flag = FeatureFixture({'sitesearch.engine.name': 'bing'})


def setUp_bing(test):
    setUpGlobs(test, future=True)
    bing_flag.setUp()


def tearDown_bing(test):
    bing_flag.cleanUp()
    tearDown(test)


special = {
    'tales.txt': LayeredDocFileSuite(
        '../doc/tales.txt',
        setUp=lambda test: setUp(test, future=True), tearDown=tearDown,
        layer=LaunchpadFunctionalLayer,
        ),
    'menus.txt': LayeredDocFileSuite(
        '../doc/menus.txt',
        setUp=lambda test: setGlobs(test, future=True), layer=None,
        ),
    'stories/launchpad-search(Bing)': PageTestSuite(
        '../stories/launchpad-search/',
        id_extensions=['site-search.txt(Bing)'],
        setUp=setUp_bing, tearDown=tearDown_bing,
        ),
    # Run these doctests again with the default search engine.
    '../stories/launchpad-search': PageTestSuite(
        '../stories/launchpad-search/',
        setUp=lambda test: setUpGlobs(test, future=True), tearDown=tearDown,
        ),
    }


def test_suite():
    return build_test_suite(
        here, special, setUp=lambda test: setUp(test, future=True))
