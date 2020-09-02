# Copyright 2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for configuring and retrieving a statsd client."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type
__all__ = ['IStatsdClient']


from zope.interface import Interface


class IStatsdClient(Interface):
    """Marker interface for retrieving a statsd client for Launchpad.

    The returned object is a statsd client as defined at
    https://statsd.readthedocs.io/en/latest/reference.html#StatsClient; we
    do not currently define a full Zope interface for it.
    """

    def reload():
        """Reload the statsd client configuration."""
