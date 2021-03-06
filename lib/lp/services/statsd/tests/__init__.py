# Copyright 2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Utility mixins for testing statsd handling"""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type
__all__ = ['StatsMixin']

from fixtures import MockPatchObject
from zope.component import getUtility

from lp.services.compat import mock
from lp.services.statsd.interfaces.statsd_client import IStatsdClient


class StatsMixin:

    def setUpStats(self):
        # Install a mock statsd client so we can assert against the call
        # counts and args.
        self.pushConfig("statsd", environment="test")
        statsd_client = getUtility(IStatsdClient)
        self.stats_client = mock.Mock()
        self.useFixture(
            MockPatchObject(statsd_client, "_client", self.stats_client))
