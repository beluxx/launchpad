# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'BinaryPackageReleaseContents',
    ]

import tempfile

from apt.debfile import DebPackage
from bzrlib.osutils import pumpfile
from storm.locals import (
    Int,
    Reference,
    Storm,
    )
from zope.component import getUtility
from zope.interface import implements

from canonical.launchpad.interfaces.lpstorm import IMasterStore
from lp.soyuz.interfaces.binarypackagepath import IBinaryPackagePathSet
from lp.soyuz.interfaces.binarypackagereleasecontents import (
    IBinaryPackageReleaseContents,
    )


class BinaryPackageReleaseContents(Storm):
    """See `IBinaryPackageReleaseContents`."""
    implements(IBinaryPackageReleaseContents)
    __storm_table__ = 'BinaryPackageReleaseContents'
    __storm_primary__ = ("binarypackagerelease_id", "binaypackagepath_id")

    binarypackagerelease_id = Int(
        name='binarypackagerelease', allow_none=False)
    binarypackagerelease = Reference(
        binarypackagerelease_id, 'BinaryPackageRelease.id')

    binaypackagepath_id = Int(name='binarypackagepath', allow_none=False)
    binarypackagepath = Reference(
        binaypackagepath_id, 'BinaryPackagePath.id')

    def add(self, bpr):
        """See `IBinaryPackageReleaseContentsSet`."""
        if not bpr.files:
            return None
        store = IMasterStore(BinaryPackageReleaseContents)
        dest_file = tempfile.NamedTemporaryFile()
        bpr.files[0].libraryfile.open()
        pumpfile(bpr.files[0].libraryfile, dest_file)
        dest_file.seek(0)
        deb = DebPackage(filename=dest_file.name)
        dest_file.close()
        # Filter out directories.
        filelist = filter(lambda x: not x.endswith('/'), deb.filelist)
        for filename in filelist:
            bpp = getUtility(IBinaryPackagePathSet).getOrCreate(
                unicode(filename))
            bprc = BinaryPackageReleaseContents()
            bprc.binarypackagerelease = bpr
            bprc.binarypackagepath = bpp
            store.add(bprc)

    def remove(self, bpr):
        """See `IBinaryPackageReleaseContentsSet`."""
        store = IMasterStore(BinaryPackageReleaseContents)
        results = store.find(
            BinaryPackageReleaseContents,
            BinaryPackageReleaseContents.binarypackagerelease == bpr.id)
        results.remove()
