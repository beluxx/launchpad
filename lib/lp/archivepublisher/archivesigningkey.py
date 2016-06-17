# Copyright 2009-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""ArchiveSigningKey implementation."""

__metaclass__ = type

__all__ = [
    'ArchiveSigningKey',
    ]


import os

import gpgme
from zope.component import getUtility
from zope.interface import implementer

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.archivepublisher.config import getPubConfig
from lp.archivepublisher.interfaces.archivesigningkey import (
    IArchiveSigningKey,
    )
from lp.registry.interfaces.gpg import IGPGKeySet
from lp.services.config import config
from lp.services.gpg.interfaces import IGPGHandler
from lp.services.propertycache import get_property_cache


@implementer(IArchiveSigningKey)
class ArchiveSigningKey:
    """`IArchive` adapter for manipulating its GPG key."""

    def __init__(self, archive):
        self.archive = archive

    @property
    def _archive_root_path(self):
        return getPubConfig(self.archive).archiveroot

    def getPathForSecretKey(self, key):
        """See `IArchiveSigningKey`."""
        return os.path.join(
            config.personalpackagearchive.signing_keys_root,
            "%s.gpg" % key.fingerprint)

    def exportSecretKey(self, key):
        """See `IArchiveSigningKey`."""
        assert key.secret, "Only secret keys should be exported."
        export_path = self.getPathForSecretKey(key)

        if not os.path.exists(os.path.dirname(export_path)):
            os.makedirs(os.path.dirname(export_path))

        export_file = open(export_path, 'w')
        export_file.write(key.export())
        export_file.close()

    def generateSigningKey(self):
        """See `IArchiveSigningKey`."""
        assert self.archive.signing_key is None, (
            "Cannot override signing_keys.")

        # Always generate signing keys for the default PPA, even if it
        # was not expecifically requested. The default PPA signing key
        # is then propagated to the context named-ppa.
        default_ppa = self.archive.owner.archive
        if self.archive != default_ppa:
            if default_ppa.signing_key is None:
                IArchiveSigningKey(default_ppa).generateSigningKey()
            key = default_ppa.signing_key
            self.archive.signing_key_owner = key.owner
            self.archive.signing_key_fingerprint = key.fingerprint
            del get_property_cache(self.archive).signing_key
            return

        key_displayname = (
            "Launchpad PPA for %s" % self.archive.owner.displayname)
        secret_key = getUtility(IGPGHandler).generateKey(key_displayname)
        self._setupSigningKey(secret_key)

    def setSigningKey(self, key_path):
        """See `IArchiveSigningKey`."""
        assert self.archive.signing_key is None, (
            "Cannot override signing_keys.")
        assert os.path.exists(key_path), (
            "%s does not exist" % key_path)

        secret_key = getUtility(IGPGHandler).importSecretKey(
            open(key_path).read())
        self._setupSigningKey(secret_key)

    def _setupSigningKey(self, secret_key):
        """Mandatory setup for signing keys.

        * Export the secret key into the protected disk location.
        * Upload public key to the keyserver.
        * Store the public GPGKey reference in the database and update
          the context archive.signing_key.
        """
        self.exportSecretKey(secret_key)

        gpghandler = getUtility(IGPGHandler)
        pub_key = gpghandler.retrieveKey(secret_key.fingerprint)
        gpghandler.uploadPublicKey(pub_key.fingerprint)

        key_owner = getUtility(ILaunchpadCelebrities).ppa_key_guard
        key, _ = getUtility(IGPGKeySet).activate(
            key_owner, pub_key, pub_key.can_encrypt)
        self.archive.signing_key_owner = key.owner
        self.archive.signing_key_fingerprint = key.fingerprint
        del get_property_cache(self.archive).signing_key

    def signRepository(self, suite):
        """See `IArchiveSigningKey`."""
        assert self.archive.signing_key is not None, (
            "No signing key available for %s" % self.archive.displayname)

        suite_path = os.path.join(self._archive_root_path, 'dists', suite)
        release_file_path = os.path.join(suite_path, 'Release')
        assert os.path.exists(release_file_path), (
            "Release file doesn't exist in the repository: %s"
            % release_file_path)

        secret_key_export = open(
            self.getPathForSecretKey(self.archive.signing_key)).read()

        gpghandler = getUtility(IGPGHandler)
        secret_key = gpghandler.importSecretKey(secret_key_export)

        release_file_content = open(release_file_path).read()
        signature = gpghandler.signContent(
            release_file_content, secret_key, mode=gpgme.SIG_MODE_DETACH)

        release_signature_file = open(
            os.path.join(suite_path, 'Release.gpg'), 'w')
        release_signature_file.write(signature)
        release_signature_file.close()

        inline_release = gpghandler.signContent(
            release_file_content, secret_key, mode=gpgme.SIG_MODE_CLEAR)

        inline_release_file = open(
            os.path.join(suite_path, 'InRelease'), 'w')
        inline_release_file.write(inline_release)
        inline_release_file.close()

    def signFile(self, path):
        """See `IArchiveSigningKey`."""
        assert self.archive.signing_key is not None, (
            "No signing key available for %s" % self.archive.displayname)

        # NOTE: uses os.sep to prevent /var/tmp/../tmpFOO attacks.
        archive_root = self._archive_root_path + os.sep
        path = os.path.realpath(path)
        assert path.startswith(archive_root), (
            "Attempting to sign file (%s) outside archive_root for %s" % (
                path, self.archive.displayname))

        secret_key_export = open(
            self.getPathForSecretKey(self.archive.signing_key)).read()
        gpghandler = getUtility(IGPGHandler)
        secret_key = gpghandler.importSecretKey(secret_key_export)

        file_content = open(path).read()
        signature = gpghandler.signContent(
            file_content, secret_key, mode=gpgme.SIG_MODE_DETACH)

        with open(os.path.join(path + '.gpg'), 'w') as signature_file:
            signature_file.write(signature)
