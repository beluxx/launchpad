# Copyright 2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database classes to manage signing keys stored at the signing service."""


__metaclass__ = type

__all__ = [
    'SigningKey',
    'ArchiveSigningKey',
    'ArchiveSigningKeySet'
    ]

import base64
from collections import defaultdict

import pytz
from storm.exceptions import IntegrityError
from storm.locals import (
    DateTime,
    Int,
    RawStr,
    Reference,
    Unicode,
    )
from zope.component import getUtility
from zope.interface import implementer
from zope.interface.declarations import provider

from lp.services.database.constants import (
    DEFAULT,
    UTC_NOW,
    )
from lp.services.database.enumcol import DBEnum
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.database.stormbase import StormBase
from lp.services.signing.enums import (
    SigningKeyType,
    SigningMode,
    )
from lp.services.signing.interfaces.signingkey import (
    IArchiveSigningKey,
    IArchiveSigningKeySet,
    ISigningKey,
    ISigningKeySet,
    )
from lp.services.signing.interfaces.signingserviceclient import (
    ISigningServiceClient,
    )


@implementer(ISigningKey)
@provider(ISigningKeySet)
class SigningKey(StormBase):
    """A key stored at lp-signing, used to sign uploaded files and packages"""

    __storm_table__ = 'SigningKey'

    id = Int(primary=True)

    key_type = DBEnum(enum=SigningKeyType, allow_none=False)

    description = Unicode(allow_none=True)

    fingerprint = Unicode(allow_none=False)

    public_key = RawStr(allow_none=False)

    date_created = DateTime(
        allow_none=False, default=UTC_NOW, tzinfo=pytz.UTC)

    def __init__(self, key_type, fingerprint, public_key,
                 description=None, date_created=DEFAULT):
        """Builds the signing key

        :param key_type: One of the SigningKeyType enum items
        :param fingerprint: The key's fingerprint
        :param public_key: The key's public key (raw; not base64-encoded)
        """
        super(SigningKey, self).__init__()
        self.key_type = key_type
        self.fingerprint = fingerprint
        self.public_key = public_key
        self.description = description
        self.date_created = date_created

    @classmethod
    def generate(cls, key_type, description=None):
        signing_service = getUtility(ISigningServiceClient)
        generated_key = signing_service.generate(key_type, description)
        signing_key = SigningKey(
            key_type=key_type, fingerprint=generated_key['fingerprint'],
            public_key=generated_key['public-key'],
            description=description)
        store = IMasterStore(SigningKey)
        store.add(signing_key)
        return signing_key

    def sign(self, message, message_name):
        if self.key_type in (SigningKeyType.UEFI, SigningKeyType.FIT):
            mode = SigningMode.ATTACHED
        else:
            mode = SigningMode.DETACHED
        signing_service = getUtility(ISigningServiceClient)
        signed = signing_service.sign(
            self.key_type, self.fingerprint, message_name, message, mode)
        return signed['signed-message']


@implementer(IArchiveSigningKey)
class ArchiveSigningKey(StormBase):
    """Which signing key should be used by a given archive / series.
    """

    __storm_table__ = 'ArchiveSigningKey'

    id = Int(primary=True)

    archive_id = Int(name="archive", allow_none=False)
    archive = Reference(archive_id, 'Archive.id')

    distro_series_id = Int(name="distro_series", allow_none=True)
    distro_series = Reference(distro_series_id, 'DistroSeries.id')

    signing_key_id = Int(name="signing_key", allow_none=False)
    signing_key = Reference(signing_key_id, SigningKey.id)

    def __init__(self, archive=None, distro_series=None, signing_key=None):
        super(ArchiveSigningKey, self).__init__()
        self.archive = archive
        self.signing_key = signing_key
        self.distro_series = distro_series


@implementer(IArchiveSigningKeySet)
class ArchiveSigningKeySet:

    @classmethod
    def create(cls, archive, distro_series, signing_key):
        store = IMasterStore(SigningKey)
        obj = ArchiveSigningKey(archive, distro_series, signing_key)
        store.add(obj)
        return obj

    @classmethod
    def getSigningKey(cls, key_type, archive, distro_series):
        # Gets all the keys available for the given archive.
        store = IStore(ArchiveSigningKey)
        rs = store.find(ArchiveSigningKey,
                SigningKey.id == ArchiveSigningKey.signing_key_id,
                SigningKey.key_type == key_type,
                ArchiveSigningKey.archive == archive)

        # prefetch related signing keys to avoid extra queries.
        signing_keys = store.find(SigningKey, [
            SigningKey.id.is_in([i.signing_key_id for i in rs])])
        signing_keys_by_id = {i.id: i for i in signing_keys}

        # Group keys per type, and per distro series
        keys_per_series = defaultdict(dict)
        for i in rs:
            signing_key = signing_keys_by_id[i.signing_key_id]
            keys_per_series[i.distro_series] = signing_key

        ret_keys = {}

        # Let's search the most suitable per key type.
        found_series = False
        for series in archive.distribution.series:
            if series == distro_series:
                found_series = True
            if found_series and series in keys_per_series:
                return keys_per_series[series]
        # If no specific key for distro_series was found, returns
        # the keys for the archive itself (or None if no key is
        # available for the archive either).
        return keys_per_series.get(None)

    @classmethod
    def generate(cls, key_type, archive, distro_series=None,
                 description=None):
        signing_key = SigningKey.generate(key_type, description)
        archive_signing = ArchiveSigningKeySet.create(
            archive, distro_series, signing_key)
        return archive_signing
