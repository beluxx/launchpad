# Copyright 2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the Launchpad statsd client"""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type

from statsd import StatsClient
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.services.config import config
from lp.services.statsd.interfaces.lp_statsd_client import ILPStatsdClient
from lp.services.statsd.model.lp_statsd_client import (
    LPStatsdClient,
    UnconfiguredStatsdClient,
    )
from lp.testing import TestCase
from lp.testing.layers import ZopelessLayer


class TestClientConfiguration(TestCase):

    layer = ZopelessLayer

    def test_accessible_via_utility(self):
        """Test that we can access the class via a zope utility."""
        config.push(
            'statsd_test',
            "[statsd]\nhost: 127.0.01\nport: 9999\nprefix: test\n")
        client = getUtility(ILPStatsdClient).getClient()
        self.assertEqual(type(client), StatsClient)

    def test_get_correct_instance_unconfigured(self):
        """Test that we get the correct client, depending on config values."""
        config.push(
            'statsd_test',
            "[statsd]\nhost:")
        client = LPStatsdClient().getClient()
        self.assertEqual(type(client), UnconfiguredStatsdClient)

    def test_get_correct_instance_configured(self):
        config.push(
            'statsd_test',
            "[statsd]\nhost: 127.0.01\nport: 9999\nprefix: test\n")
        client = LPStatsdClient().getClient()
        self.assertEqual(type(client), StatsClient)
