# Copyright 2008 Canonical Ltd.  All rights reserved.

"""An SFTP server that backs on to a special kind of Bazaar Transport.

The Bazaar Transport is special in two ways:

 1. It implements two methods `writeChunk` and `local_realPath` (see the
    `FatLocalTransport` class for a description of these)
 2. Every transport method returns Deferreds and does not block.

We call such a transport a "Twisted Transport".
"""

__all__ = ['AvatarToSFTPAdapter', 'TransportSFTPServer']
__metaclass__ = type


import errno
import os
import stat

from bzrlib import errors as bzr_errors
from bzrlib import osutils, urlutils
from bzrlib.transport.local import LocalTransport
from twisted.conch.ssh import filetransfer
from twisted.conch.interfaces import ISFTPFile, ISFTPServer
from twisted.internet import defer
from twisted.python import util
from zope.interface import implements

from canonical.codehosting.transport import (
    AsyncLaunchpadTransport, LaunchpadServer)
from canonical.config import config
from canonical.twistedsupport import gatherResults


class FileIsADirectory(bzr_errors.PathError):
    """Raised when writeChunk is called on a directory.

    This exists mainly to be translated into the appropriate SFTP error.
    """

    _fmt = 'File is a directory: %(path)r%(extra)s'


class FatLocalTransport(LocalTransport):
    """A Bazaar transport that also implements writeChunk and local_realPath.

    We need these so that we can implement SFTP over a Bazaar transport.
    """

    def writeChunk(self, name, offset, data):
        """Write a chunk of data to file `name` at `offset`."""
        abspath = self._abspath(name)
        osutils.check_legal_path(abspath)
        try:
            chunk_file = os.open(abspath, os.O_CREAT | os.O_WRONLY)
        except OSError, e:
            if e.errno != errno.EISDIR:
                raise
            raise FileIsADirectory(name)
        os.lseek(chunk_file, offset, 0)
        os.write(chunk_file, data)
        os.close(chunk_file)

    def local_realPath(self, path):
        """Return the absolute path to `path`."""
        abspath = self._abspath(path)
        return urlutils.escape(os.path.realpath(abspath))


def with_sftp_error(func):
    """Decorator used to translate Bazaar errors into SFTP errors.

    This assumes that the function being decorated returns a Deferred.

    See `TransportSFTPServer.translateError` for the details of the
    translation.
    """
    def decorator(*args, **kwargs):
        deferred = func(*args, **kwargs)
        return deferred.addErrback(TransportSFTPServer.translateError,
                                   func.__name__)
    return util.mergeFunctionMetadata(func, decorator)


class TransportSFTPFile:
    """An implementation of `ISFTPFile` that backs onto a Bazaar transport.

    The transport must be a Twisted Transport.
    """

    implements(ISFTPFile)

    def __init__(self, transport, name, flags, server):
        self._unescaped_relpath = name
        self._escaped_path = urlutils.escape(self._unescaped_relpath)
        self._flags = flags
        self.transport = transport
        self._written = False
        self._server = server

    def _shouldAppend(self):
        """Is this file opened append?"""
        return bool(self._flags & filetransfer.FXF_APPEND)

    def _shouldCreate(self):
        """Should we create a file?"""
        # The Twisted VFS adapter creates a file when any of these flags are
        # set. It's possible that we only need to check for FXF_CREAT.
        create_mask = (
            filetransfer.FXF_WRITE | filetransfer.FXF_APPEND |
            filetransfer.FXF_CREAT)
        return bool(self._flags & create_mask)

    def _shouldTruncate(self):
        """Should we truncate the file?"""
        return (bool(self._flags & filetransfer.FXF_TRUNC)
                and not self._written)

    def _shouldWrite(self):
        """Is this file opened writable?"""
        write_mask = (filetransfer.FXF_WRITE | filetransfer.FXF_APPEND)
        return bool(self._flags & write_mask)

    def _truncateFile(self):
        """Truncate this file."""
        self._written = True
        return self.transport.put_bytes(self._escaped_path, '')

    @with_sftp_error
    def writeChunk(self, offset, data):
        """See `ISFTPFile`."""
        if not self._shouldWrite():
            raise filetransfer.SFTPError(
                filetransfer.FX_PERMISSION_DENIED,
                "%r was opened read-only." % self._unescaped_relpath)
        if self._shouldTruncate():
            deferred = self._truncateFile()
        else:
            deferred = defer.succeed(None)
        self._written = True
        if self._shouldAppend():
            deferred.addCallback(
                lambda ignored:
                self.transport.append_bytes(self._escaped_path, data))
        else:
            deferred.addCallback(
                lambda ignored:
                self.transport.writeChunk(self._escaped_path, offset, data))
        return deferred

    @with_sftp_error
    def readChunk(self, offset, length):
        """See `ISFTPFile`."""
        deferred = self.transport.readv(
            self._escaped_path, [(offset, length)])
        def get_first_chunk(read_things):
            return read_things.next()[1]
        def handle_short_read(failure):
            """Handle short reads by reading what was available.

            Doing things this way around, by trying to read all the data
            requested and then handling the short read error, might be a bit
            inefficient, but the bzrlib sftp transport doesn't read past the
            end of files, so we don't need to worry too much about performance
            here.
            """
            failure.trap(bzr_errors.ShortReadvError)
            return self.readChunk(failure.value.offset, failure.value.actual)
        deferred.addCallback(get_first_chunk)
        return deferred.addErrback(handle_short_read)

    def setAttrs(self, attrs):
        """See `ISFTPFile`.

        The Transport interface does not allow setting any attributes.
        """
        # XXX 2008-05-09 JonathanLange: This should at least raise an error,
        # not do nothing silently.
        return self._server.setAttrs(self._unescaped_relpath, attrs)

    @with_sftp_error
    def getAttrs(self):
        """See `ISFTPFile`."""
        return self._server.getAttrs(self._unescaped_relpath, False)

    def close(self):
        """See `ISFTPFile`."""
        if self._written or not self._shouldCreate():
            return defer.succeed(None)

        if self._shouldTruncate():
            return self._truncateFile()

        deferred = self.transport.has(self._escaped_path)
        def maybe_create_file(already_exists):
            if not already_exists:
                return self._truncateFile()
        return deferred.addCallback(maybe_create_file)


def _get_transport_for_dir(directory):
    url = urlutils.local_path_to_url(directory)
    return FatLocalTransport(url)


def avatar_to_sftp_server(avatar):
    user_id = avatar.user_id
    hosted_transport = _get_transport_for_dir(
        config.codehosting.branches_root)
    mirror_transport = _get_transport_for_dir(
        config.supermirror.branchesdest)
    server = LaunchpadServer(
        avatar.branchfs_proxy, user_id, hosted_transport, mirror_transport)
    server.setUp()
    transport = AsyncLaunchpadTransport(server, server.get_url())
    return TransportSFTPServer(transport)


class TransportSFTPServer:
    """An implementation of `ISFTPServer` that backs onto a Bazaar transport.

    The transport must be a Twisted Transport.
    """

    implements(ISFTPServer)

    def __init__(self, transport):
        self.transport = transport

    def extendedRequest(self, extendedName, extendedData):
        """See `ISFTPServer`."""
        raise NotImplementedError

    def makeLink(self, src, dest):
        """See `ISFTPServer`."""
        raise NotImplementedError()

    @with_sftp_error
    def openDirectory(self, path):
        """See `ISFTPServer`."""
        class DirectoryListing:
            """Class to satisfy openDirectory return interface.

            openDirectory returns an iterator -- with a `close` method.  Hence
            this class.
            """

            def __init__(self, entries):
                self.iter = iter(entries)

            def __iter__(self):
                return self

            def next(self):
                return self.iter.next()

            def close(self):
                # I can't believe we had to implement a whole class just to
                # have this do-nothing method (abentley).
                pass

        deferred = self.transport.list_dir(urlutils.escape(path))
        def format_attrs(attrs, unescaped):
            return (unescaped, unescaped, attrs)
        def stat_files(file_list):
            deferreds = []
            for f in file_list:
                unescaped = urlutils.unescape(f).encode('utf-8')
                unescaped_path = os.path.join(path, unescaped)
                attr_deferred = self.getAttrs(unescaped_path, False)
                attr_deferred.addCallback(format_attrs, unescaped)
                deferreds.append(attr_deferred)
            return gatherResults(deferreds)
        return deferred.addCallback(stat_files).addCallback(DirectoryListing)

    @with_sftp_error
    def openFile(self, path, flags, attrs):
        """See `ISFTPServer`."""
        directory = os.path.dirname(path)
        deferred = self.transport.stat(directory)
        def open_file(stat_result):
            if stat.S_ISDIR(stat_result.st_mode):
                return TransportSFTPFile(self.transport, path, flags, self)
            else:
                raise filetransfer.SFTPError(
                    filetransfer.FX_NO_SUCH_FILE, directory)
        return deferred.addCallback(open_file)

    def readLink(self, path):
        """See `ISFTPServer`."""
        raise NotImplementedError()

    def realPath(self, relpath):
        """See `ISFTPServer`."""
        deferred = self.transport.local_realPath(urlutils.escape(relpath))
        def unescape_path(path):
            unescaped_path = urlutils.unescape(path)
            return unescaped_path.encode('utf-8')
        return deferred.addCallback(unescape_path)

    def setAttrs(self, path, attrs):
        """See `ISFTPServer`.

        This just delegates to TransportSFTPFile's implementation.
        """
        return defer.succeed(None)

    @with_sftp_error
    def getAttrs(self, path, followLinks):
        """See `ISFTPServer`.

        This just delegates to TransportSFTPFile's implementation.
        """
        deferred = self.transport.stat(urlutils.escape(path))
        def translate_stat(stat_val):
            return {
                'size': getattr(stat_val, 'st_size', 0),
                'uid': getattr(stat_val, 'st_uid', 0),
                'gid': getattr(stat_val, 'st_gid', 0),
                'permissions': getattr(stat_val, 'st_mode', 0),
                'atime': getattr(stat_val, 'st_atime', 0),
                'mtime': getattr(stat_val, 'st_mtime', 0),
            }
        return deferred.addCallback(translate_stat)

    def gotVersion(self, otherVersion, extensionData):
        """See `ISFTPServer`."""
        return {}

    @with_sftp_error
    def makeDirectory(self, path, attrs):
        """See `ISFTPServer`."""
        return self.transport.mkdir(
            urlutils.escape(path), attrs['permissions'])

    @with_sftp_error
    def removeDirectory(self, path):
        """See `ISFTPServer`."""
        return self.transport.rmdir(urlutils.escape(path))

    @with_sftp_error
    def removeFile(self, path):
        """See `ISFTPServer`."""
        return self.transport.delete(urlutils.escape(path))

    @with_sftp_error
    def renameFile(self, oldpath, newpath):
        """See `ISFTPServer`."""
        return self.transport.rename(
            urlutils.escape(oldpath), urlutils.escape(newpath))

    @staticmethod
    def translateError(failure, func_name):
        """Translate Bazaar errors to `filetransfer.SFTPError` instances."""
        types_to_codes = {
            bzr_errors.PermissionDenied: filetransfer.FX_PERMISSION_DENIED,
            bzr_errors.TransportNotPossible:
                filetransfer.FX_PERMISSION_DENIED,
            bzr_errors.NoSuchFile: filetransfer.FX_NO_SUCH_FILE,
            bzr_errors.FileExists: filetransfer.FX_FILE_ALREADY_EXISTS,
            bzr_errors.DirectoryNotEmpty: filetransfer.FX_FAILURE,
            FileIsADirectory: filetransfer.FX_FILE_IS_A_DIRECTORY,
            }
        # Bazaar expects makeDirectory to fail with exactly the string "mkdir
        # failed".
        names_to_messages = {
            'makeDirectory': 'mkdir failed',
            }
        try:
            sftp_code = types_to_codes[failure.type]
        except KeyError:
            failure.raiseException()
        message = names_to_messages.get(func_name, failure.getErrorMessage())
        raise filetransfer.SFTPError(sftp_code, message)
