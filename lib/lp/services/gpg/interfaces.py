# Copyright 2009-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__all__ = [
    'GPG_DATABASE_READONLY_FEATURE_FLAG',
    'GPG_HIDE_PERSON_KEY_LISTING',
    'GPG_READ_FROM_GPGSERVICE_FEATURE_FLAG',
    'GPG_WRITE_TO_GPGSERVICE_FEATURE_FLAG',
    'GPGKeyAlgorithm',
    'GPGKeyDoesNotExistOnServer',
    'GPGKeyExpired',
    'GPGKeyNotFoundError',
    'GPGKeyRevoked',
    'GPGKeyTemporarilyNotFoundError',
    'GPGReadOnly',
    'GPGServiceException',
    'GPGUploadFailure',
    'GPGVerificationError',
    'IGPGClient',
    'IGPGHandler',
    'IPymeKey',
    'IPymeSignature',
    'IPymeUserId',
    'MoreThanOneGPGKeyFound',
    'SecretGPGKeyImportDetected',
    'valid_fingerprint',
    'valid_keyid',
    ]

import httplib
import re

from gpgservice_client import GPGServiceException
from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from lazr.restful.declarations import error_status
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.security.interfaces import Forbidden


@error_status(httplib.FORBIDDEN)
class GPGReadOnly(Forbidden):
    """GPG Service is in read-only mode."""

    def __init__(self):
        super(GPGReadOnly, self).__init__(
            "The GPG key storage facilities of Launchpad are currently "
            "read-only. Please try again later.")


GPG_DATABASE_READONLY_FEATURE_FLAG = u"gpg.database_read_only"
GPG_WRITE_TO_GPGSERVICE_FEATURE_FLAG = u"gpg.write_to_gpgservice"
GPG_READ_FROM_GPGSERVICE_FEATURE_FLAG = u"gpg.read_from_gpgservice"
GPG_HIDE_PERSON_KEY_LISTING = u"gpg.hide_person_key_listing"


def valid_fingerprint(fingerprint):
    """Is the fingerprint of valid form."""
    # Fingerprints of v3 keys are md5, fingerprints of v4 keys are sha1;
    # accordingly, fingerprints of v3 keys are 128 bit, those of v4 keys
    # 160. Check therefore for strings of hex characters that are 32
    # (4 * 32 == 128) or 40 characters long (4 * 40 = 160).
    if len(fingerprint) not in (32, 40):
        return False
    if re.match(r"^[\dA-F]+$", fingerprint) is None:
        return False
    return True


def valid_keyid(keyid):
    """Is the key of valid form."""
    if re.match(r"^[\dA-F]{8}$", keyid) is not None:
        return True
    else:
        return False


# XXX: cprov 2004-10-04:
# (gpg+dbschema) the data structure should be rearranged to support 4 field
# needed: keynumber(1,16,17,20), keyalias(R,g,D,G), title and description
class GPGKeyAlgorithm(DBEnumeratedType):
    """
    GPG Compliant Key Algorithms Types:

    1 : "R", # RSA
    16: "g", # ElGamal
    17: "D", # DSA
    20: "G", # ElGamal, compromised

    FIXME
    Rewrite it according to the experimental API returning also a name
    attribute tested on 'algorithmname' attribute

    """

    R = DBItem(1, """
        R

        RSA""")

    LITTLE_G = DBItem(16, """
         g

         ElGamal""")

    D = DBItem(17, """
        D

        DSA""")

    G = DBItem(20, """
        G

        ElGamal, compromised""")


class MoreThanOneGPGKeyFound(Exception):
    """More than one GPG key was found.

    And we don't know which one to import.
    """


class GPGKeyNotFoundError(Exception):
    """The GPG key with the given fingerprint was not found on the keyserver.
    """

    def __init__(self, fingerprint, message=None):
        self.fingerprint = fingerprint
        if message is None:
            message = (
            "No GPG key found with the given content: %s" % (fingerprint, ))
        super(GPGKeyNotFoundError, self).__init__(message)


class GPGKeyTemporarilyNotFoundError(GPGKeyNotFoundError):
    """The GPG key with the given fingerprint was not found on the keyserver.

    The reason is a timeout while accessing the server, a general
    server error, a network problem or some other temporary issue.
    """
    def __init__(self, fingerprint):
        message = (
            "GPG key %s not found due to a server or network failure."
            % fingerprint)
        super(GPGKeyTemporarilyNotFoundError, self).__init__(
            fingerprint, message)


class GPGKeyDoesNotExistOnServer(GPGKeyNotFoundError):
    """The GPG key with the given fingerprint was not found on the keyserver.

    The server returned an explicit "not found".
    """
    def __init__(self, fingerprint):
        message = (
            "GPG key %s does not exist on the keyserver." % fingerprint)
        super(GPGKeyDoesNotExistOnServer, self).__init__(
            fingerprint, message)


class GPGKeyRevoked(Exception):
    """The given GPG key was revoked."""

    def __init__(self, key):
        self.key = key
        super(GPGKeyRevoked, self).__init__(
            "%s has been publicly revoked" % (key.keyid, ))


class GPGKeyExpired(Exception):
    """The given GPG key has expired."""

    def __init__(self, key):
        self.key = key
        super(GPGKeyExpired, self).__init__("%s has expired" % (key.keyid, ))


class SecretGPGKeyImportDetected(Exception):
    """An attempt to import a secret GPG key."""


class GPGUploadFailure(Exception):
    """Raised when a key upload failed.

    Typically when a keyserver is not reachable.
    """


class GPGVerificationError(Exception):
    """OpenPGP verification error."""


class IGPGHandler(Interface):
    """Handler to perform OpenPGP operations."""

    def sanitizeFingerprint(fingerprint):
        """Return sanitized fingerprint if well-formed.

        If the firgerprint cannot be sanitized return None.
        """

    def verifySignature(content, signature=None):
        """See `getVerifiedSignature`.

        Suppress all exceptions and simply return None if the could not
        be verified.
        """

    def getURLForKeyInServer(fingerprint, action=None, public=False):
        """Return the URL for that fingerprint on the configured keyserver.

        If public is True, return a URL for the public keyserver; otherwise,
        references the default (internal) keyserver.
        If action is provided, will attach that to the URL.
        """

    def getVerifiedSignatureResilient(content, signature=None):
        """Wrapper for getVerifiedSignature.

        It calls the target method exactly 3 times.

        Return the result if it succeed during the cycle, otherwise
        capture the errors and emits at the end GPGVerificationError
        with the stored error information.
        """

    def getVerifiedSignature(content, signature=None):
        """Returns a PymeSignature object if content is correctly signed.

        If signature is None, we assume content is clearsigned. Otherwise
        it stores the detached signature and content should contain the
        plain text in question.

        content and signature must be 8-bit encoded str objects. It's up to
        the caller to encode or decode as appropriate.

        The only exception likely to be propogated out is GPGVerificationError

        :param content: The content to be verified as string;
        :param signature: The signature as string (or None if content is
            clearsigned)

        :raise GPGVerificationError: if the signature cannot be verified.
        :return: a `PymeSignature` object.
        """

    def importPublicKey(content):
        """Import the given public key into our local keyring.

        If the secret key's ASCII armored content is given,
        SecretGPGKeyDetected is raised.

        If no key is found, GPGKeyNotFoundError is raised.  On the other
        hand, if more than one key is found, MoreThanOneGPGKeyFound is
        raised.

        :param content: public key ASCII armored content (must be an ASCII
            string (it's up to the caller to encode or decode properly);
        :return: a `PymeKey` object referring to the public key imported.
        """

    def importSecretKey(content):
        """Import the given secret key into our local keyring.

        If no key is found, GPGKeyNotFoundError is raised.  On the other
        hand, if more than one key is found, MoreThanOneGPGKeyFound is
        raised.

        :param content: secret key ASCII armored content (must be an ASCII
            string (it's up to the caller to encode or decode properly);
        :return: a `PymeKey` object referring to the secret key imported.
        """

    def generateKey(name):
        """Generate a new GPG key with the given name.

        Currently only passwordless, signo-only 1024-bit RSA keys are
        generated.

        :param name: unicode to be included in the key paramenters, 'comment'
            and 'email' will be empty. It's content will be encoded to
            'utf-8' internally.
        :raise AssertionError: if the key generation is not exaclty what
            we expect.

        :return: a `PymeKey` object for the just-generated secret key.
        """

    def encryptContent(content, key):
        """Encrypt the given content for the given key.

        content must be a traditional string. It's up to the caller to
        encode or decode properly.

        :param content: the Unicode content to be encrypted.
        :param key: the `IPymeKey` to encrypt the content for.

        :return: the encrypted content or None if failed.
        """

    def signContent(content, key, password='', mode=None):
        """Signs content with a given GPG key.

        :param content: the content to sign.
        :param key: the `IPymeKey` to use when signing the content.
        :param password: optional password to the key identified by
            key_fingerprint, the default value is '',
        :param mode: optional type of GPG signature to produce, the
            default mode is gpgme.SIG_MODE_CLEAR (clearsigned signatures)

        :return: The ASCII-armored signature for the content.
        """

    def retrieveKey(fingerprint):
        """Retrieve the key information from the local keyring.

        If the key with the given fingerprint is not present in the local
        keyring, first import it from the key server into the local keyring.

        :param fingerprint: The key fingerprint, which must be an hexadecimal
            string.
        :raise GPGKeyNotFoundError: if the key is not found neither in the
            local keyring nor in the key server.
        :return: a `PymeKey`object containing the key information.
        """

    def retrieveActiveKey(fingerprint):
        """Retrieve key information, raise errors if the key is not active.

        Exactly like `retrieveKey` except raises errors if the key is expired
        or has been revoked.

        :param fingerprint: The key fingerprint, which must be an hexadecimal
            string.
        :raise GPGKeyNotFoundError: if the key is not found neither in the
            local keyring nor in the key server.
        :return: a `PymeKey`object containing the key information.
        """

    def uploadPublicKey(fingerprint):
        """Upload the specified public key to a keyserver.

        Use `retrieveKey` to get the public key content and upload an
        ASCII-armored export chunk.

        :param fingerprint: The key fingerprint, which must be an hexadecimal
            string.
        :raise GPGUploadFailure: if the keyserver could not be reaches.
        :raise AssertionError: if the POST request doesn't succeed.
        """

    def localKeys(filter=None, secret=False):
        """Return an iterator of all keys locally known about.

        :param filter: optional string used to filter the results. By default
            gpgme tries to match '<name> [comment] [email]', the full
            fingerprint or the key ID (fingerprint last 8 digits);
        :param secret: optional boolean, restrict the domain to secret or
            public keys available in the keyring. Defaults to False.

        :return: a `PymeKey` generator with the matching keys.
        """

    def resetLocalState():
        """Reset the local state.

        Resets OpenPGP keyrings and trust database.
        """
        #FIXME RBC: this should be a zope test cleanup thing per SteveA.


class IPymeSignature(Interface):
    """pyME signature container."""

    fingerprint = Attribute("Signer Fingerprint.")
    plain_data = Attribute("Plain Signed Text.")
    timestamp = Attribute("The time at which the message was signed.")


class IPymeKey(Interface):
    """pyME key model."""

    fingerprint = Attribute("Key Fingerprint")
    key = Attribute("Underlying GpgmeKey object")
    algorithm = Attribute("Key Algorithm")
    revoked = Attribute("Key Revoked")
    expired = Attribute("Key Expired")
    secret = Attribute("Whether the key is secret of not.")
    keysize = Attribute("Key Size")
    keyid = Attribute("Pseudo Key ID, composed by last fingerprint 8 digits ")
    uids = Attribute("List of user IDs associated with this key")
    emails = Attribute(
        "List containing only well formed and non-revoked emails")
    displayname = Attribute("Key displayname: <size><type>/<keyid>")
    owner_trust = Attribute("The owner trust")

    can_encrypt = Attribute("Whether the key can be used for encrypting")
    can_sign = Attribute("Whether the key can be used for signing")
    can_certify = Attribute("Whether the key can be used for certification")
    can_authenticate = Attribute(
        "Whether the key can be used for authentication")

    def export():
        """Export the context key in ASCII-armored mode.

        Both public and secret keys are supported, although secret keys are
        exported by calling `gpg` process while public ones use the native
        gpgme API.

        :return: a string containing the exported key.
        """


class IPymeUserId(Interface):
    """pyME user ID"""

    revoked = Attribute("True if the user ID has been revoked")
    invalid = Attribute("True if the user ID is invalid")
    validity = Attribute("""A measure of the validity of the user ID,
                         based on owner trust values and signatures.""")
    uid = Attribute("A string identifying this user ID")
    name = Attribute("The name portion of this user ID")
    email = Attribute("The email portion of this user ID")
    comment = Attribute("The comment portion of this user ID")


class IGPGClient(Interface):

    """A client for querying a gpgservice instance."""

    def getKeysForOwner(owner_id):
        """Get a list of keys for a given owner.

        :raises GPGServiceException: If we get an error from the gpgservice.
        :raises socket.error" on socket-level errors (connection timeouts etc)
        """

    def addKeyForOwner(owner_id, fingerprint):
        """Add a GPG key.

        :raises ValueError: if the fingerprint isn't valid.
        :raises GPGServiceException: If we get an error from the gpgservice.
        :raises socket.error" on socket-level errors (connection timeouts etc)
        """

    def disableKeyForOwner(owner_id, fingerprint):
        """Disable a GPG key.

        :raises ValueError: if the fingerprint isn't valid.
        :raises GPGServiceException: If we get an error from the gpgservice.
        :raises socket.error" on socket-level errors (connection timeouts etc)
        """

    def getKeyByFingerprint(fingerprint):
        """Get a GPG key by its fingerprint.

        :raises ValueError: if the fingerprint isn't valid.
        """

    def getKeysByFingerprints(fingerprints):
        """Bulk retrieve GPG keys by a list of fingerprints.

        :param fingerprints: A list of fingerprints to retrieve.
        :returns: A list of keys that were found.
        """

    def registerWriteHook(hook_callable):
        """Register a write hook.

        The hook_callable will be called with no arguments whenever an operation
        is performed that modifies the GPG database.

        :raises TypeError: if hook_callable is not a callable.
        :raises GPGServiceException: If we get an error from the gpgservice.
        """

    def unregisterWriteHook(hook_callable):
        """Deregister a write hook that was registered with register_write_hook.

        :raises ValueError: if hook_callable was not registered.
        """

    def addKeyForTest(owner_id, keyid, fingerprint, keysize, algorithm, enabled,
                      can_encrypt):
        """Add a key to the gpgservice without checking the keyserver.

        This method is to be used for TESTING purposes only. The running
        gpgservice instance must have its test methods configured - something
        that should not be done in production. If this requirement is not met
        a RuntimeError will be raised.

        :param owner_id: A string representing the owner, as returned by
                         IGPGKeySet.getOwnerIdForPerson
        :param keyid: A string describing the short-form gpg key id.
        :param fingerprint: A string containing the full GPG fingerprint.
        :param keysize: An integer, containing the keysize.
        :param algorithm: The key algorithm code, a single letter.
        :param enabled: Whether the key is enabled or not.
        :param can_encrypt: Whether the key can be used for encryption.
        """
