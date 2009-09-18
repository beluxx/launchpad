# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bugs-specific testing infrastructure for Windmill."""

__metaclass__ = type
__all__ = [
    'BugsWindmillLayer',
    ]


from canonical.testing.layers import BaseWindmillLayer


class BugsWindmillLayer(BaseWindmillLayer):
    """Layer for Bugs Windmill tests."""

    base_url = 'http://bugs.launchpad.dev:8085/'
