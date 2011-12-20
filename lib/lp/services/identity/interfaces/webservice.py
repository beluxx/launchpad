# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""All the interfaces that are exposed through the webservice.

There is a declaration in ZCML somewhere that looks like:
  <webservice:register module="canonical.launchpad.interfaces.webservice" />

which tells `lazr.restful` that it should look for webservice exports here.
"""

__metaclass__ = type
__all__ = [
    'IEmailAddress',
    ]

from canonical.launchpad.components.apihelpers import (
    patch_entry_explicit_version,
    )
from lp.services.identity.interfaces.emailaddress import IEmailAddress


# IEmailAddress
patch_entry_explicit_version(IEmailAddress, 'beta')
