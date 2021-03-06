# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from __future__ import absolute_import, print_function, unicode_literals

from lp.services.webapp import GetitemNavigation
from lp.services.worlddata.interfaces.country import ICountrySet


class CountrySetNavigation(GetitemNavigation):
    usedfor = ICountrySet
