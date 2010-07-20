# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Source Package Recipe vocabularies used in the lp/code modules."""
from zope.component import getUtility
from zope.schema.vocabulary import SimpleVocabulary, SimpleTerm

from canonical.launchpad.interfaces import ILaunchBag
from canonical.launchpad.webapp.authorization import check_permission
from canonical.launchpad.webapp.sorting import sorted_dotted_numbers
from lp.registry.interfaces.distroseries import IDistroSeriesSet
from lp.soyuz.browser.archive import make_archive_vocabulary
from lp.soyuz.interfaces.archive import IArchiveSet


def get_buildable_distroseries_set(user):
    ppas = getUtility(IArchiveSet).getPPAsForUser(user)
    supported_distros = [ppa.distribution for ppa in ppas]
    distros = getUtility(IDistroSeriesSet).search()

    buildables = []
    for distro in distros:
        if distro.active and distro.distribution in supported_distros:
            buildables.append(distro)
    return buildables


def buildable_distroseries_vocabulary(context):
    """Return a vocabulary of buildable distroseries."""
    distros = get_buildable_distroseries_set(getUtility(ILaunchBag).user)
    terms = sorted_dotted_numbers(
        [SimpleTerm(distro, distro.id, distro.displayname)
         for distro in distros],
        key=lambda term: term.value.version)
    terms.reverse()
    return SimpleVocabulary(terms)


def target_ppas_vocabulary(context):
    """Return a vocabulary of ppas that the current user can target."""
    ppas = getUtility(IArchiveSet).getPPAsForUser(getUtility(ILaunchBag).user)
    return make_archive_vocabulary(
        ppa for ppa in ppas
        if check_permission('launchpad.Append', ppa))
