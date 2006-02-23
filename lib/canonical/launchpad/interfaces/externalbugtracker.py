# Copyright 2006 Canonical Ltd.  All rights reserved.

"""Interfaces declarations for external bugtrackers."""

__metaclass__ = type

__all__ = [
    'IExternalBugtracker',
    ]

from zope.interface import Interface


class IExternalBugtracker(Interface):
    """A class used to talk with an external bug tracker."""

    def updateBugWatches(bug_watches):
        """Update the given bug watches."""

    def malone_status(remote_status):
        """Converts the remote status string to a Malone status string.

        Return 'UNKNOWN' if it can't be converted.
        """
