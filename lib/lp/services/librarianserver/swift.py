# Copyright 2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Move files from Librarian disk storage into Swift."""

__metaclass__ = type
__all__ = [
    'to_swift', 'filesystem_path', 'swift_location',
    'connection', 'connection_pool', 'SWIFT_CONTAINER_PREFIX',
    ]

from contextlib import contextmanager
import os.path
import sys
import time

from swiftclient import client as swiftclient

from lp.services.config import config


SWIFT_CONTAINER_PREFIX = 'librarian_'
MAX_SWIFT_OBJECT_SIZE = 5 * 1024 ** 3  # 5GB Swift limit.


def to_swift(log, start_lfc_id=None, end_lfc_id=None, remove=False):
    '''Copy a range of Librarian files from disk into Swift.

    start and end identify the range of LibraryFileContent.id to
    migrate (inclusive).

    If remove is True, files are removed from disk after being copied into
    Swift.
    '''
    swift_connection = connection_pool.get()
    fs_root = os.path.abspath(config.librarian_server.root)

    if start_lfc_id is None:
        start_lfc_id = 1
    if end_lfc_id is None:
        end_lfc_id = sys.maxint
        end_str = 'MAXINT'
    else:
        end_str = str(end_lfc_id)

    log.info("Walking disk store {0} from {1} to {2}, inclusive".format(
        fs_root, start_lfc_id, end_str))

    start_fs_path = filesystem_path(start_lfc_id)
    end_fs_path = filesystem_path(end_lfc_id)

    # Walk the Librarian on disk file store, searching for matching
    # files that may need to be copied into Swift. We need to follow
    # symlinks as they are being used span disk partitions.
    for dirpath, dirnames, filenames in os.walk(fs_root, followlinks=True):

        # Don't recurse if we know this directory contains no matching
        # files.
        if (start_fs_path[:len(dirpath)] > dirpath
            or end_fs_path[:len(dirpath)] < dirpath):
            dirnames[:] = []
            continue

        log.debug('Scanning {0} for matching files'.format(dirpath))

        for filename in sorted(filenames):
            fs_path = os.path.join(dirpath, filename)
            if fs_path < start_fs_path:
                continue
            if fs_path > end_fs_path:
                break

            # Skip files which have been modified recently, as they
            # may be uploads still in progress.
            if os.path.getmtime(fs_path) > time.time() - (60 * 60):
                log.debug('Skipping recent upload %s' % fs_path)
                continue

            # Reverse engineer the LibraryFileContent.id from the
            # file's path. Warn about and skip bad filenames.
            rel_fs_path = fs_path[len(fs_root) + 1:]
            hex_lfc = ''.join(rel_fs_path.split('/'))
            if len(hex_lfc) != 8:
                log.warning(
                    'Filename length fail, skipping {0}'.format(fs_path))
                continue
            try:
                lfc = int(hex_lfc, 16)
            except ValueError:
                log.warning('Invalid hex fail, skipping {0}'.format(fs_path))
                continue

            log.debug('Found {0} ({1})'.format(lfc, filename))

            container, obj_name = swift_location(lfc)

            try:
                swift_connection.head_container(container)
                log.debug2('{0} container already exists'.format(container))
            except swiftclient.ClientException as x:
                if x.http_status != 404:
                    raise
                log.info('Creating {0} container'.format(container))
                swift_connection.put_container(container)

            try:
                swift_connection.head_object(container, obj_name)
                log.debug(
                    "{0} already exists in Swift({1}, {2})".format(
                        lfc, container, obj_name))
            except swiftclient.ClientException as x:
                if x.http_status != 404:
                    raise
                log.info(
                    'Putting {0} into Swift ({1}, {2})'.format(
                        lfc, container, obj_name))
                _put(swift_connection, container, obj_name, fs_path)

            if remove:
                os.unlink(fs_path)


def _put(swift_connection, container, obj_name, fs_path):
    fs_size = os.path.getsize(fs_path)
    fs_file = open(fs_path, 'rb')
    if fs_size <= MAX_SWIFT_OBJECT_SIZE:
        swift_connection.put_object(container, obj_name, fs_file, fs_size)
    else:
        # Large file upload. Create the segments first, then the
        # manifest. This order prevents partial downloads, and lets us
        # detect interrupted uploads and clean up.
        segment = 0
        while fs_file.tell() < fs_size:
            assert segment <= 9999, 'Insane number of segments'
            seg_name = '%s/%04d' % (obj_name, segment)
            swift_connection.put_object(
                container, seg_name, fs_file, MAX_SWIFT_OBJECT_SIZE)
            segment = segment + 1
        manifest = '%s/%s/' % (
            urllib.quote(container, urllib.quote(obj_name)))
        manifest_headers = {'x-object-manifest': manifest}
        swift_connection.put_object(
            container, obj_name, '', 0, headers=manifest_headers)


def swift_location(lfc_id):
    '''Return the (container, obj_name) used to store a file.

    Per https://answers.launchpad.net/swift/+question/181977, we can't
    simply stuff everything into one container.
    '''
    assert isinstance(lfc_id, (int, long)), 'Not a LibraryFileContent.id'

    # Don't change this unless you are also going to rebuild the Swift
    # storage, as objects will no longer be found in the expected
    # container. This value and the container prefix are deliberatly
    # hard coded to avoid cockups with values specified in config files.
    # While the suggested number is 'under a million', the rare large files
    # will take up multiple slots so we choose a more conservative number.
    max_objects_per_container = 500000

    container_num = lfc_id // max_objects_per_container

    return (SWIFT_CONTAINER_PREFIX + str(container_num), str(lfc_id))


def filesystem_path(lfc_id):
    from lp.services.librarianserver.storage import _relFileLocation
    return os.path.join(
        config.librarian_server.root, _relFileLocation(lfc_id))


class SwiftStream:
    def __init__(self, swift_connection, chunks):
        self._swift_connection = swift_connection
        self._chunks = chunks  # Generator from swiftclient.get_object()

        self.closed = False
        self._offset = 0
        self._chunk = None

    def read(self, size):
        if self.closed:
            raise ValueError('I/O operation on closed file')

        if self._swift_connection is None:
            return ''

        if size == 0:
            return ''

        return_chunks = []
        return_size = 0

        while return_size < size:
            if not self._chunk:
                self._chunk = self._next_chunk()
                if not self._chunk:
                    # If we have drained the data successfully,
                    # the connection can be reused saving on auth
                    # handshakes.
                    connection_pool.put(self._swift_connection)
                    self._swift_connection = None
                    self._chunks = None
                    break
            split = size - return_size
            return_chunks.append(self._chunk[:split])
            self._chunk = self._chunk[split:]
            return_size += len(return_chunks[-1])

        self._offset += return_size
        return ''.join(return_chunks)

    def _next_chunk(self):
        try:
            return self._chunks.next()
        except StopIteration:
            return None

    def close(self):
        self.closed = True
        self._swift_connection = None

    def seek(self, offset):
        if offset < self._offset:
            raise NotImplementedError('rewind')  # Rewind not supported
        else:
            self.read(offset - self._offset)

    def tell(self):
        return self._offset


class ConnectionPool:
    MAX_POOL_SIZE = 10

    def __init__(self):
        self.clear()

    def clear(self):
        self._pool = []

    def get(self):
        '''Return a conection from the pool, or a fresh connection.'''
        try:
            return self._pool.pop()
        except IndexError:
            return self._new_connection()

    def put(self, swift_connection):
        '''Put a connection back in the pool for reuse.

        Only call this if the connection is in a usable state. If an
        exception has been raised (apart from a 404), don't trust the
        swift_connection and throw it away.
        '''
        if swift_connection not in self._pool:
            self._pool.append(swift_connection)
            while len(self._pool) > self.MAX_POOL_SIZE:
                self._pool.pop(0)

    def _new_connection(self):
        return swiftclient.Connection(
            authurl=os.environ.get('OS_AUTH_URL', None),
            user=os.environ.get('OS_USERNAME', None),
            key=os.environ.get('OS_PASSWORD', None),
            tenant_name=os.environ.get('OS_TENANT_NAME', None),
            auth_version='2.0',
            )


connection_pool = ConnectionPool()


@contextmanager
def connection():
    global connection_pool
    con = connection_pool.get()
    yield con

    # We can safely put the connection back in the pool, as this code is
    # only reached if the contextmanager block exited normally (no
    # exception raised).
    connection_pool.put(con)
