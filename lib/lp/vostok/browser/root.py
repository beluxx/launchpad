# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser code for the Vostok root."""

__metaclass__ = type
__all__ = [
    'VostokRootView',
    ]

from zope.component import getUtility

from canonical.launchpad.webapp import LaunchpadView

from lp.registry.interfaces.distribution import IDistributionSet


class VostokRootView(LaunchpadView):
    """The view for the Vostok root object."""

    @property
    def distributions(self):
        """An iterable of all registered distributions."""
        return getUtility(IDistributionSet)
