# Copyright 2009-2019 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the code import worker."""

__metaclass__ = type

import logging
import os
import shutil
import subprocess
import tempfile
import time
from uuid import uuid4

from bzrlib import (
    trace,
    urlutils,
    )
from bzrlib.branch import (
    Branch,
    BranchReferenceFormat,
    )
from bzrlib.branchbuilder import BranchBuilder
from bzrlib.bzrdir import (
    BzrDir,
    BzrDirFormat,
    format_registry,
    )
from bzrlib.errors import NoSuchFile
from bzrlib.tests import (
    http_utils,
    TestCaseWithTransport,
    )
from bzrlib.transport import (
    get_transport,
    get_transport_from_url,
    )
from bzrlib.url_policy_open import (
    _BlacklistPolicy,
    AcceptAnythingPolicy,
    BadUrl,
    BranchOpener,
    BranchOpenPolicy,
    )
from bzrlib.urlutils import (
    join as urljoin,
    local_path_from_url,
    )
from CVS import (
    Repository,
    tree as CVSTree,
    )
from dulwich.repo import Repo as GitRepo
from fixtures import FakeLogger
import scandir
import subvertpy
import subvertpy.client
import subvertpy.ra

import lp.codehosting
from lp.codehosting.codeimport.tarball import (
    create_tarball,
    extract_tarball,
    )
from lp.codehosting.codeimport.tests.servers import (
    BzrServer,
    CVSServer,
    GitServer,
    SubversionServer,
    )
from lp.codehosting.codeimport.worker import (
    BazaarBranchStore,
    BzrImportWorker,
    BzrSvnImportWorker,
    CodeImportBranchOpenPolicy,
    CodeImportSourceDetails,
    CodeImportWorkerExitCode,
    CSCVSImportWorker,
    ForeignTreeStore,
    get_default_bazaar_branch_store,
    GitImportWorker,
    ImportDataStore,
    ToBzrImportWorker,
    )
from lp.codehosting.tests.helpers import create_branch_with_one_revision
from lp.services.config import config
from lp.services.log.logger import BufferLogger
from lp.testing import TestCase
from lp.testing.layers import BaseLayer


class ForeignBranchPluginLayer(BaseLayer):
    """Ensure only specific tests are run with foreign branch plugins loaded.
    """

    @classmethod
    def setUp(cls):
        pass

    @classmethod
    def tearDown(cls):
        # Raise NotImplementedError to signal that this layer cannot be torn
        # down.  This means that the test runner will run subsequent tests in
        # a different process.
        raise NotImplementedError

    @classmethod
    def testSetUp(cls):
        pass

    @classmethod
    def testTearDown(cls):
        pass


default_format = BzrDirFormat.get_default_format()


class WorkerTest(TestCaseWithTransport, TestCase):
    """Base test case for things that test the code import worker.

    Provides Bazaar testing features, access to Launchpad objects and
    factories for some code import objects.
    """

    layer = ForeignBranchPluginLayer

    def setUp(self):
        super(WorkerTest, self).setUp()
        self.disable_directory_isolation()
        BranchOpener.install_hook()

    def assertDirectoryTreesEqual(self, directory1, directory2):
        """Assert that `directory1` has the same structure as `directory2`.

        That is, assert that all of the files and directories beneath
        `directory1` are laid out in the same way as `directory2`.
        """
        def list_files(directory):
            for path, ignored, ignored in scandir.walk(directory):
                yield path[len(directory):]
        self.assertEqual(
            sorted(list_files(directory1)), sorted(list_files(directory2)))

    def makeTemporaryDirectory(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory)
        return directory


class TestBazaarBranchStore(WorkerTest):
    """Tests for `BazaarBranchStore`."""

    def setUp(self):
        WorkerTest.setUp(self)
        # XXX: JonathanLange 2010-12-24 bug=694140: Avoid spurious "No
        # handlers for logger 'bzr'" messages.
        trace._bzr_logger = logging.getLogger('bzr')
        self.temp_dir = self.makeTemporaryDirectory()
        self.arbitrary_branch_id = 10

    def makeBranchStore(self):
        return BazaarBranchStore(self.get_transport())

    def test_defaultStore(self):
        # The default store is at config.codeimport.bazaar_branch_store.
        store = get_default_bazaar_branch_store()
        self.assertEqual(
            store.transport.base.rstrip('/'),
            config.codeimport.bazaar_branch_store.rstrip('/'))

    def test__getMirrorURL(self):
        # _getMirrorURL returns a URL for the branch with the given id.
        store = BazaarBranchStore(get_transport_from_url(
            'sftp://storage.example/branches'))
        self.assertEqual(
            'sftp://storage.example/branches/000186a0',
            store._getMirrorURL(100000))

    def test__getMirrorURL_push(self):
        # _getMirrorURL prefers bzr+ssh over sftp when constructing push
        # URLs.
        store = BazaarBranchStore(get_transport_from_url(
            'sftp://storage.example/branches'))
        self.assertEqual(
            'bzr+ssh://storage.example/branches/000186a0',
            store._getMirrorURL(100000, push=True))

    def test_getNewBranch(self):
        # If there's no Bazaar branch of this id, then pull creates a new
        # Bazaar branch.
        store = self.makeBranchStore()
        bzr_branch = store.pull(
            self.arbitrary_branch_id, self.temp_dir, default_format)
        self.assertEqual(0, bzr_branch.revno())

    def test_getNewBranch_without_tree(self):
        # If pull() with needs_tree=False creates a new branch, it doesn't
        # create a working tree.
        store = self.makeBranchStore()
        bzr_branch = store.pull(
            self.arbitrary_branch_id, self.temp_dir, default_format, False)
        self.assertFalse(bzr_branch.bzrdir.has_workingtree())

    def test_getNewBranch_with_tree(self):
        # If pull() with needs_tree=True creates a new branch, it creates a
        # working tree.
        store = self.makeBranchStore()
        bzr_branch = store.pull(
            self.arbitrary_branch_id, self.temp_dir, default_format, True)
        self.assertTrue(bzr_branch.bzrdir.has_workingtree())

    def test_pushBranchThenPull(self):
        # After we've pushed up a branch to the store, we can then pull it
        # from the store.
        store = self.makeBranchStore()
        tree = create_branch_with_one_revision('original')
        store.push(self.arbitrary_branch_id, tree.branch, default_format)
        new_branch = store.pull(
            self.arbitrary_branch_id, self.temp_dir, default_format)
        self.assertEqual(
            tree.branch.last_revision(), new_branch.last_revision())

    def test_pull_without_needs_tree_doesnt_create_tree(self):
        # pull with needs_tree=False doesn't spend the time to create a
        # working tree.
        store = self.makeBranchStore()
        tree = create_branch_with_one_revision('original')
        store.push(self.arbitrary_branch_id, tree.branch, default_format)
        new_branch = store.pull(
            self.arbitrary_branch_id, self.temp_dir, default_format, False)
        self.assertFalse(new_branch.bzrdir.has_workingtree())

    def test_pull_needs_tree_creates_tree(self):
        # pull with needs_tree=True creates a working tree.
        store = self.makeBranchStore()
        tree = create_branch_with_one_revision('original')
        store.push(self.arbitrary_branch_id, tree.branch, default_format)
        new_branch = store.pull(
            self.arbitrary_branch_id, self.temp_dir, default_format, True)
        self.assertTrue(new_branch.bzrdir.has_workingtree())

    def test_pullUpgradesFormat(self):
        # A branch should always be in the most up-to-date format before a
        # pull is performed.
        store = self.makeBranchStore()
        target_url = store._getMirrorURL(self.arbitrary_branch_id)
        knit_format = format_registry.get('knit')()
        tree = create_branch_with_one_revision(target_url, format=knit_format)
        self.assertNotEqual(
            tree.bzrdir._format.repository_format.network_name(),
            default_format.repository_format.network_name())

        # The fetched branch is in the default format.
        new_branch = store.pull(
            self.arbitrary_branch_id, self.temp_dir, default_format)
        # Make sure backup.bzr is removed, as it interferes with CSCVS.
        self.assertEqual(os.listdir(self.temp_dir), [".bzr"])
        self.assertEqual(new_branch.repository._format.network_name(),
            default_format.repository_format.network_name())

    def test_pushUpgradesFormat(self):
        # A branch should always be in the most up-to-date format before a
        # pull is performed.
        store = self.makeBranchStore()
        target_url = store._getMirrorURL(self.arbitrary_branch_id)
        knit_format = format_registry.get('knit')()
        create_branch_with_one_revision(target_url, format=knit_format)

        # The fetched branch is in the default format.
        new_branch = store.pull(
            self.arbitrary_branch_id, self.temp_dir, default_format)
        self.assertEqual(
            default_format, new_branch.bzrdir._format)

        # The remote branch is still in the old format at this point.
        target_branch = Branch.open(target_url)
        self.assertEqual(
            knit_format.get_branch_format(),
            target_branch._format)

        store.push(self.arbitrary_branch_id, new_branch, default_format)

        # The remote branch is now in the new format.
        target_branch = Branch.open(target_url)
        # Only .bzr is left behind. The scanner removes branches
        # in which invalid directories (such as .bzr.retire.
        # exist). (bug #798560)
        self.assertEqual(
            target_branch.user_transport.list_dir("."),
            [".bzr"])
        self.assertEqual(
            default_format.get_branch_format(),
            target_branch._format)
        self.assertEqual(
            target_branch.last_revision_info(),
            new_branch.last_revision_info())

    def test_pushTwiceThenPull(self):
        # We can push up a branch to the store twice and then pull it from the
        # store.
        store = self.makeBranchStore()
        tree = create_branch_with_one_revision('original')
        store.push(self.arbitrary_branch_id, tree.branch, default_format)
        store.push(self.arbitrary_branch_id, tree.branch, default_format)
        new_branch = store.pull(
            self.arbitrary_branch_id, self.temp_dir, default_format)
        self.assertEqual(
            tree.branch.last_revision(), new_branch.last_revision())

    def test_push_divergant_branches(self):
        # push() uses overwrite=True, so divergent branches (rebased) can be
        # pushed.
        store = self.makeBranchStore()
        tree = create_branch_with_one_revision('original')
        store.push(self.arbitrary_branch_id, tree.branch, default_format)
        tree = create_branch_with_one_revision('divergant')
        store.push(self.arbitrary_branch_id, tree.branch, default_format)

    def fetchBranch(self, from_url, target_path):
        """Pull a branch from `from_url` to `target_path`.

        This uses the Bazaar API for pulling a branch, and is used to test
        that `push` indeed pushes a branch to a specific location.

        :return: The working tree of the branch.
        """
        bzr_dir = BzrDir.open(from_url)
        bzr_dir.sprout(target_path)
        return BzrDir.open(target_path).open_workingtree()

    def test_makesDirectories(self):
        # push() tries to create the base directory of the branch store if it
        # doesn't already exist.
        store = BazaarBranchStore(self.get_transport('doesntexist'))
        tree = create_branch_with_one_revision('original')
        store.push(self.arbitrary_branch_id, tree.branch, default_format)
        self.assertIsDirectory('doesntexist', self.get_transport())

    def test_storedLocation(self):
        # push() puts the branch in a directory named after the branch ID on
        # the BazaarBranchStore's transport.
        store = self.makeBranchStore()
        tree = create_branch_with_one_revision('original')
        store.push(self.arbitrary_branch_id, tree.branch, default_format)
        new_branch = self.fetchBranch(
            urljoin(store.transport.base, '%08x' % self.arbitrary_branch_id),
            'new_tree')
        self.assertEqual(
            tree.branch.last_revision(), new_branch.last_revision())

    def test_sftpPrefix(self):
        # Since branches are mirrored by importd via sftp, _getMirrorURL must
        # support sftp urls. There was once a bug that made it incorrect with
        # sftp.
        sftp_prefix = 'sftp://example/base/'
        store = BazaarBranchStore(get_transport(sftp_prefix))
        self.assertEqual(
            store._getMirrorURL(self.arbitrary_branch_id),
            sftp_prefix + '%08x' % self.arbitrary_branch_id)

    def test_sftpPrefixNoSlash(self):
        # If the prefix has no trailing slash, one should be added. It's very
        # easy to forget a trailing slash in the importd configuration.
        sftp_prefix_noslash = 'sftp://example/base'
        store = BazaarBranchStore(get_transport(sftp_prefix_noslash))
        self.assertEqual(
            store._getMirrorURL(self.arbitrary_branch_id),
            sftp_prefix_noslash + '/' + '%08x' % self.arbitrary_branch_id)

    def test_all_revisions_saved(self):
        # All revisions in the branch's repo are transferred, not just those
        # in the ancestry of the tip.
        # Consider a branch with two heads in its repo:
        #            revid
        #           /     \
        #       revid1   revid2 <- branch tip
        # A naive push/pull would just store 'revid' and 'revid2' in the
        # branch store -- we need to make sure all three revisions are stored
        # and retrieved.
        builder = self.make_branch_builder('tree')
        revid = builder.build_snapshot(
            None, None, [('add', ('', 'root-id', 'directory', ''))])
        revid1 = builder.build_snapshot(None, [revid], [])
        revid2 = builder.build_snapshot(None, [revid], [])
        store = self.makeBranchStore()
        store.push(
            self.arbitrary_branch_id, builder.get_branch(), default_format)
        retrieved_branch = store.pull(
            self.arbitrary_branch_id, 'pulled', default_format)
        self.assertEqual(
            set([revid, revid1, revid2]),
            set(retrieved_branch.repository.all_revision_ids()))

    def test_pull_doesnt_bring_backup_directories(self):
        # If the branch has been upgraded in the branch store, `pull` does not
        # copy the backup.bzr directory to `target_path`, just the .bzr
        # directory.
        store = self.makeBranchStore()
        tree = create_branch_with_one_revision('original')
        store.push(self.arbitrary_branch_id, tree.branch, default_format)
        t = get_transport(store._getMirrorURL(self.arbitrary_branch_id))
        t.mkdir('backup.bzr')
        retrieved_branch = store.pull(
            self.arbitrary_branch_id, 'pulled', default_format,
            needs_tree=False)
        self.assertEqual(
            ['.bzr'], retrieved_branch.bzrdir.root_transport.list_dir('.'))


class TestImportDataStore(WorkerTest):
    """Tests for `ImportDataStore`."""

    def test_fetch_returnsFalseIfNotFound(self):
        # If the requested file does not exist on the transport, fetch returns
        # False.
        filename = '%s.tar.gz' % (self.factory.getUniqueString(),)
        source_details = self.factory.makeCodeImportSourceDetails()
        store = ImportDataStore(self.get_transport(), source_details)
        ret = store.fetch(filename)
        self.assertFalse(ret)

    def test_fetch_doesntCreateFileIfNotFound(self):
        # If the requested file does not exist on the transport, no local file
        # is created.
        filename = '%s.tar.gz' % (self.factory.getUniqueString(),)
        source_details = self.factory.makeCodeImportSourceDetails()
        store = ImportDataStore(self.get_transport(), source_details)
        store.fetch(filename)
        self.assertFalse(os.path.exists(filename))

    def test_fetch_returnsTrueIfFound(self):
        # If the requested file exists on the transport, fetch returns True.
        source_details = self.factory.makeCodeImportSourceDetails()
        # That the remote name is like this is part of the interface of
        # ImportDataStore.
        remote_name = '%08x.tar.gz' % (source_details.target_id,)
        local_name = '%s.tar.gz' % (self.factory.getUniqueString(),)
        transport = self.get_transport()
        transport.put_bytes(remote_name, '')
        store = ImportDataStore(transport, source_details)
        ret = store.fetch(local_name)
        self.assertTrue(ret)

    def test_fetch_retrievesFileIfFound(self):
        # If the requested file exists on the transport, fetch copies its
        # content to the filename given to fetch.
        source_details = self.factory.makeCodeImportSourceDetails()
        # That the remote name is like this is part of the interface of
        # ImportDataStore.
        remote_name = '%08x.tar.gz' % (source_details.target_id,)
        content = self.factory.getUniqueString()
        transport = self.get_transport()
        transport.put_bytes(remote_name, content)
        store = ImportDataStore(transport, source_details)
        local_name = '%s.tar.gz' % (self.factory.getUniqueString('tarball'),)
        store.fetch(local_name)
        self.assertEqual(content, open(local_name).read())

    def test_fetch_with_dest_transport(self):
        # The second, optional, argument to fetch is the transport in which to
        # place the retrieved file.
        source_details = self.factory.makeCodeImportSourceDetails()
        # That the remote name is like this is part of the interface of
        # ImportDataStore.
        remote_name = '%08x.tar.gz' % (source_details.target_id,)
        content = self.factory.getUniqueString()
        transport = self.get_transport()
        transport.put_bytes(remote_name, content)
        store = ImportDataStore(transport, source_details)
        local_prefix = self.factory.getUniqueString()
        self.get_transport(local_prefix).ensure_base()
        local_name = '%s.tar.gz' % (self.factory.getUniqueString(),)
        store.fetch(local_name, self.get_transport(local_prefix))
        self.assertEqual(
            content, open(os.path.join(local_prefix, local_name)).read())

    def test_put_copiesFileToTransport(self):
        # Put copies the content of the passed filename to the remote
        # transport.
        local_name = '%s.tar.gz' % (self.factory.getUniqueString(),)
        source_details = self.factory.makeCodeImportSourceDetails()
        content = self.factory.getUniqueString()
        get_transport('.').put_bytes(local_name, content)
        transport = self.get_transport()
        store = ImportDataStore(transport, source_details)
        store.put(local_name)
        # That the remote name is like this is part of the interface of
        # ImportDataStore.
        remote_name = '%08x.tar.gz' % (source_details.target_id,)
        self.assertEqual(content, transport.get_bytes(remote_name))

    def test_put_ensures_base(self):
        # Put ensures that the directory pointed to by the transport exists.
        local_name = '%s.tar.gz' % (self.factory.getUniqueString(),)
        subdir_name = self.factory.getUniqueString()
        source_details = self.factory.makeCodeImportSourceDetails()
        get_transport('.').put_bytes(local_name, '')
        transport = self.get_transport()
        store = ImportDataStore(transport.clone(subdir_name), source_details)
        store.put(local_name)
        self.assertTrue(transport.has(subdir_name))

    def test_put_with_source_transport(self):
        # The second, optional, argument to put is the transport from which to
        # read the retrieved file.
        local_prefix = self.factory.getUniqueString()
        local_name = '%s.tar.gz' % (self.factory.getUniqueString(),)
        source_details = self.factory.makeCodeImportSourceDetails()
        content = self.factory.getUniqueString()
        os.mkdir(local_prefix)
        get_transport(local_prefix).put_bytes(local_name, content)
        transport = self.get_transport()
        store = ImportDataStore(transport, source_details)
        store.put(local_name, self.get_transport(local_prefix))
        # That the remote name is like this is part of the interface of
        # ImportDataStore.
        remote_name = '%08x.tar.gz' % (source_details.target_id,)
        self.assertEqual(content, transport.get_bytes(remote_name))


class MockForeignWorkingTree:
    """Working tree that records calls to checkout and update."""

    def __init__(self, local_path):
        self.local_path = local_path
        self.log = []

    def checkout(self):
        self.log.append('checkout')

    def update(self):
        self.log.append('update')


class TestForeignTreeStore(WorkerTest):
    """Tests for the `ForeignTreeStore` object."""

    def assertCheckedOut(self, tree):
        self.assertEqual(['checkout'], tree.log)

    def assertUpdated(self, tree):
        self.assertEqual(['update'], tree.log)

    def setUp(self):
        """Set up a code import for an SVN working tree."""
        super(TestForeignTreeStore, self).setUp()
        self.temp_dir = self.makeTemporaryDirectory()

    def makeForeignTreeStore(self, source_details=None):
        """Make a foreign tree store.

        The store is in a different directory to the local working directory.
        """
        def _getForeignTree(target_path):
            return MockForeignWorkingTree(target_path)
        fake_it = False
        if source_details is None:
            fake_it = True
            source_details = self.factory.makeCodeImportSourceDetails()
        transport = self.get_transport('remote')
        store = ForeignTreeStore(ImportDataStore(transport, source_details))
        if fake_it:
            store._getForeignTree = _getForeignTree
        return store

    def test_getForeignTreeCVS(self):
        # _getForeignTree() returns a CVS working tree for CVS code imports.
        source_details = self.factory.makeCodeImportSourceDetails(
            rcstype='cvs')
        store = self.makeForeignTreeStore(source_details)
        working_tree = store._getForeignTree('path')
        self.assertIsSameRealPath(working_tree.local_path, 'path')
        self.assertEqual(working_tree.root, source_details.cvs_root)
        self.assertEqual(working_tree.module, source_details.cvs_module)

    def test_getNewWorkingTree(self):
        # If the foreign tree store doesn't have an archive of the foreign
        # tree, then fetching the tree actually pulls in from the original
        # site.
        store = self.makeForeignTreeStore()
        tree = store.fetchFromSource(self.temp_dir)
        self.assertCheckedOut(tree)

    def test_archiveTree(self):
        # Once we have a foreign working tree, we can archive it so that we
        # can retrieve it more reliably in the future.
        store = self.makeForeignTreeStore()
        foreign_tree = store.fetchFromSource(self.temp_dir)
        store.archive(foreign_tree)
        transport = store.import_data_store._transport
        source_details = store.import_data_store.source_details
        self.assertTrue(
            transport.has('%08x.tar.gz' % source_details.target_id),
            "Couldn't find '%08x.tar.gz'" % source_details.target_id)

    def test_fetchFromArchiveFailure(self):
        # If a tree has not been archived yet, but we try to retrieve it from
        # the archive, we get a NoSuchFile error.
        store = self.makeForeignTreeStore()
        self.assertRaises(
            NoSuchFile,
            store.fetchFromArchive, self.temp_dir)

    def test_fetchFromArchive(self):
        # After archiving a tree, we can retrieve it from the store -- the
        # tarball gets downloaded and extracted.
        store = self.makeForeignTreeStore()
        foreign_tree = store.fetchFromSource(self.temp_dir)
        store.archive(foreign_tree)
        new_temp_dir = self.makeTemporaryDirectory()
        foreign_tree2 = store.fetchFromArchive(new_temp_dir)
        self.assertEqual(new_temp_dir, foreign_tree2.local_path)
        self.assertDirectoryTreesEqual(self.temp_dir, new_temp_dir)

    def test_fetchFromArchiveUpdates(self):
        # The local working tree is updated with changes from the remote
        # branch after it has been fetched from the archive.
        store = self.makeForeignTreeStore()
        foreign_tree = store.fetchFromSource(self.temp_dir)
        store.archive(foreign_tree)
        new_temp_dir = self.makeTemporaryDirectory()
        foreign_tree2 = store.fetchFromArchive(new_temp_dir)
        self.assertUpdated(foreign_tree2)


class TestWorkerCore(WorkerTest):
    """Tests for the core (VCS-independent) part of the code import worker."""

    def setUp(self):
        WorkerTest.setUp(self)
        self.source_details = self.factory.makeCodeImportSourceDetails()

    def makeBazaarBranchStore(self):
        """Make a Bazaar branch store."""
        return BazaarBranchStore(self.get_transport('bazaar_branches'))

    def makeImportWorker(self):
        """Make an ImportWorker."""
        return ToBzrImportWorker(
            self.source_details, self.get_transport('import_data'),
            self.makeBazaarBranchStore(), logging.getLogger("silent"),
            AcceptAnythingPolicy())

    def test_construct(self):
        # When we construct an ImportWorker, it has a CodeImportSourceDetails
        # object.
        worker = self.makeImportWorker()
        self.assertEqual(self.source_details, worker.source_details)

    def test_getBazaarWorkingBranchMakesEmptyBranch(self):
        # getBazaarBranch returns a brand-new working tree for an initial
        # import.
        worker = self.makeImportWorker()
        bzr_branch = worker.getBazaarBranch()
        self.assertEqual(0, bzr_branch.revno())

    def test_bazaarBranchLocation(self):
        # getBazaarBranch makes the working tree under the current working
        # directory.
        worker = self.makeImportWorker()
        bzr_branch = worker.getBazaarBranch()
        self.assertIsSameRealPath(
            os.path.abspath(worker.BZR_BRANCH_PATH),
            os.path.abspath(local_path_from_url(bzr_branch.base)))


class TestCSCVSWorker(WorkerTest):
    """Tests for methods specific to CSCVSImportWorker."""

    def setUp(self):
        WorkerTest.setUp(self)
        self.source_details = self.factory.makeCodeImportSourceDetails()

    def makeImportWorker(self):
        """Make a CSCVSImportWorker."""
        return CSCVSImportWorker(
            self.source_details, self.get_transport('import_data'), None,
            logging.getLogger("silent"), opener_policy=AcceptAnythingPolicy())

    def test_getForeignTree(self):
        # getForeignTree returns an object that represents the 'foreign'
        # branch (i.e. a CVS or Subversion branch).
        worker = self.makeImportWorker()

        def _getForeignTree(target_path):
            return MockForeignWorkingTree(target_path)

        worker.foreign_tree_store._getForeignTree = _getForeignTree
        working_tree = worker.getForeignTree()
        self.assertIsSameRealPath(
            os.path.abspath(worker.FOREIGN_WORKING_TREE_PATH),
            working_tree.local_path)


class TestGitImportWorker(WorkerTest):
    """Test for behaviour particular to `GitImportWorker`."""

    def makeBazaarBranchStore(self):
        """Make a Bazaar branch store."""
        t = self.get_transport('bazaar_branches')
        t.ensure_base()
        return BazaarBranchStore(self.get_transport('bazaar_branches'))

    def makeImportWorker(self):
        """Make an GitImportWorker."""
        source_details = self.factory.makeCodeImportSourceDetails()
        return GitImportWorker(
            source_details, self.get_transport('import_data'),
            self.makeBazaarBranchStore(), logging.getLogger("silent"),
            opener_policy=AcceptAnythingPolicy())

    def test_pushBazaarBranch_saves_git_cache(self):
        # GitImportWorker.pushBazaarBranch saves a tarball of the git cache
        # from the tree's repository in the worker's ImportDataStore.
        content = self.factory.getUniqueString()
        branch = self.make_branch('.')
        branch.repository._transport.mkdir('git')
        branch.repository._transport.put_bytes('git/cache', content)
        import_worker = self.makeImportWorker()
        import_worker.pushBazaarBranch(branch)
        import_worker.import_data_store.fetch('git-cache.tar.gz')
        extract_tarball('git-cache.tar.gz', '.')
        self.assertEqual(content, open('cache').read())

    def test_getBazaarBranch_fetches_legacy_git_db(self):
        # GitImportWorker.getBazaarBranch fetches the legacy git.db file, if
        # present, from the worker's ImportDataStore into the tree's
        # repository.
        import_worker = self.makeImportWorker()
        # Store the git.db file in the store.
        content = self.factory.getUniqueString()
        open('git.db', 'w').write(content)
        import_worker.import_data_store.put('git.db')
        # Make sure there's a Bazaar branch in the branch store.
        branch = self.make_branch('branch')
        ToBzrImportWorker.pushBazaarBranch(import_worker, branch)
        # Finally, fetching the tree gets the git.db file too.
        branch = import_worker.getBazaarBranch()
        self.assertEqual(
            content, branch.repository._transport.get('git.db').read())

    def test_getBazaarBranch_fetches_git_cache(self):
        # GitImportWorker.getBazaarBranch fetches the tarball of the git
        # cache from the worker's ImportDataStore and expands it into the
        # tree's repository.
        import_worker = self.makeImportWorker()
        # Store a tarred-up cache in the store.x
        content = self.factory.getUniqueString()
        os.mkdir('cache')
        open('cache/git-cache', 'w').write(content)
        create_tarball('cache', 'git-cache.tar.gz')
        import_worker.import_data_store.put('git-cache.tar.gz')
        # Make sure there's a Bazaar branch in the branch store.
        branch = self.make_branch('branch')
        ToBzrImportWorker.pushBazaarBranch(import_worker, branch)
        # Finally, fetching the tree gets the git.db file too.
        new_branch = import_worker.getBazaarBranch()
        self.assertEqual(
            content,
            new_branch.repository._transport.get('git/git-cache').read())


def clean_up_default_stores_for_import(source_details):
    """Clean up the default branch and foreign tree stores for an import.

    This checks for an existing branch and/or other import data corresponding
    to the passed in import and deletes them if they are found.

    If there are tarballs or branches in the default stores that might
    conflict with working on our job, life gets very, very confusing.

    :source_details: A `CodeImportSourceDetails` describing the import.
    """
    tree_transport = get_transport(config.codeimport.foreign_tree_store)
    prefix = '%08x' % source_details.target_id
    if tree_transport.has('.'):
        for filename in tree_transport.list_dir('.'):
            if filename.startswith(prefix):
                tree_transport.delete(filename)
    branchstore = get_default_bazaar_branch_store()
    branch_name = '%08x' % source_details.target_id
    if branchstore.transport.has(branch_name):
        branchstore.transport.delete_tree(branch_name)


class TestActualImportMixin:
    """Mixin for tests that check the actual importing."""

    def setUpImport(self):
        """Set up the objects required for an import.

        This means a BazaarBranchStore, CodeImport and a CodeImportJob.
        """
        self.bazaar_store = BazaarBranchStore(
            self.get_transport('bazaar_store'))
        self.foreign_commit_count = 0

    def makeImportWorker(self, source_details, opener_policy):
        """Make a new `ImportWorker`.

        Override this in your subclass.
        """
        raise NotImplementedError(
            "Override this with a VCS-specific implementation.")

    def makeForeignCommit(self, source_details):
        """Commit a revision to the repo described by `self.source_details`.

        Increment `self.foreign_commit_count` as appropriate.

        Override this in your subclass.
        """
        raise NotImplementedError(
            "Override this with a VCS-specific implementation.")

    def makeWorkerArguments(self, module_name, files, stacked_on_url=None):
        """Make a list of worker arguments pointing to a real repository.

        This should set `self.foreign_commit_count` to an appropriate value.

        Override this in your subclass.
        """
        raise NotImplementedError(
            "Override this with a VCS-specific implementation.")

    def makeSourceDetails(self, module_name, files, stacked_on_url=None):
        """Make a `CodeImportSourceDetails` pointing to a real repository."""
        return CodeImportSourceDetails.fromArguments(self.makeWorkerArguments(
            module_name, files, stacked_on_url=stacked_on_url))

    def getStoredBazaarBranch(self, worker):
        """Get the Bazaar branch 'worker' stored into its BazaarBranchStore.
        """
        branch_url = worker.bazaar_branch_store._getMirrorURL(
            worker.source_details.target_id)
        return Branch.open(branch_url)

    def clearCaches(self):
        """Clear any caches between worker runs, if necessary.

        Override this in your subclass if you need it.
        """

    def test_import(self):
        # Running the worker on a branch that hasn't been imported yet imports
        # the branch.
        worker = self.makeImportWorker(self.makeSourceDetails(
            'trunk', [('README', 'Original contents')]),
            opener_policy=AcceptAnythingPolicy())
        worker.run()
        branch = self.getStoredBazaarBranch(worker)
        self.assertEqual(self.foreign_commit_count, branch.revno())

    def test_sync(self):
        # Do an import.
        worker = self.makeImportWorker(self.makeSourceDetails(
            'trunk', [('README', 'Original contents')]),
            opener_policy=AcceptAnythingPolicy())
        worker.run()
        branch = self.getStoredBazaarBranch(worker)
        self.assertEqual(self.foreign_commit_count, branch.revno())

        # Change the remote branch.
        self.makeForeignCommit(worker.source_details)

        # Run the same worker again.
        self.clearCaches()
        worker.run()

        # Check that the new revisions are in the Bazaar branch.
        branch = self.getStoredBazaarBranch(worker)
        self.assertEqual(self.foreign_commit_count, branch.revno())

    def test_import_script(self):
        # Like test_import, but using the code-import-worker.py script
        # to perform the import.
        arguments = self.makeWorkerArguments(
            'trunk', [('README', 'Original contents')])
        source_details = CodeImportSourceDetails.fromArguments(arguments)

        clean_up_default_stores_for_import(source_details)

        script_path = os.path.join(
            config.root, 'scripts', 'code-import-worker.py')
        output = tempfile.TemporaryFile()
        retcode = subprocess.call(
            [script_path, '--access-policy=anything'] + arguments,
            stderr=output, stdout=output)
        self.assertEqual(retcode, 0)

        # It's important that the subprocess writes to stdout or stderr
        # regularly to let the worker monitor know it's still alive.  That
        # specifically is hard to test, but we can at least test that the
        # process produced _some_ output.
        output.seek(0, 2)
        self.assertPositive(output.tell())

        self.addCleanup(
            lambda: clean_up_default_stores_for_import(source_details))

        tree_path = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(tree_path))

        branch_url = get_default_bazaar_branch_store()._getMirrorURL(
            source_details.target_id)
        branch = Branch.open(branch_url)

        self.assertEqual(self.foreign_commit_count, branch.revno())

    def test_script_exit_codes(self):
        # After a successful import that imports revisions, the worker exits
        # with a code of CodeImportWorkerExitCode.SUCCESS.  After a successful
        # import that does not import revisions, the worker exits with a code
        # of CodeImportWorkerExitCode.SUCCESS_NOCHANGE.
        arguments = self.makeWorkerArguments(
            'trunk', [('README', 'Original contents')])
        source_details = CodeImportSourceDetails.fromArguments(arguments)

        clean_up_default_stores_for_import(source_details)

        script_path = os.path.join(
            config.root, 'scripts', 'code-import-worker.py')
        output = tempfile.TemporaryFile()
        retcode = subprocess.call(
            [script_path, '--access-policy=anything'] + arguments,
            stderr=output, stdout=output)
        self.assertEqual(retcode, CodeImportWorkerExitCode.SUCCESS)
        retcode = subprocess.call(
            [script_path, '--access-policy=anything'] + arguments,
            stderr=output, stdout=output)
        self.assertEqual(retcode, CodeImportWorkerExitCode.SUCCESS_NOCHANGE)


class CSCVSActualImportMixin(TestActualImportMixin):

    def setUpImport(self):
        """Set up the objects required for an import.

        This sets up a ForeignTreeStore in addition to what
        TestActualImportMixin.setUpImport does.
        """
        TestActualImportMixin.setUpImport(self)

    def makeImportWorker(self, source_details, opener_policy):
        """Make a new `ImportWorker`."""
        return CSCVSImportWorker(
            source_details, self.get_transport('foreign_store'),
            self.bazaar_store, logging.getLogger(), opener_policy)


class TestCVSImport(WorkerTest, CSCVSActualImportMixin):
    """Tests for the worker importing and syncing a CVS module."""

    def setUp(self):
        super(TestCVSImport, self).setUp()
        self.useFixture(FakeLogger())
        self.setUpImport()

    def makeForeignCommit(self, source_details):
        # If you write to a file in the same second as the previous commit,
        # CVS will not think that it has changed.
        time.sleep(1)
        repo = Repository(source_details.cvs_root, BufferLogger())
        repo.get(source_details.cvs_module, 'working_dir')
        wt = CVSTree('working_dir')
        self.build_tree_contents([('working_dir/README', 'New content')])
        wt.commit(log='Log message')
        self.foreign_commit_count += 1
        shutil.rmtree('working_dir')

    def makeWorkerArguments(self, module_name, files, stacked_on_url=None):
        """Make CVS worker arguments pointing at a real CVS repo."""
        cvs_server = CVSServer(self.makeTemporaryDirectory())
        cvs_server.start_server()
        self.addCleanup(cvs_server.stop_server)

        cvs_server.makeModule('trunk', [('README', 'original\n')])

        self.foreign_commit_count = 2

        return [
            str(self.factory.getUniqueInteger()), 'cvs:bzr',
            cvs_server.getRoot(), 'trunk',
            ]


class SubversionImportHelpers:
    """Implementations of `makeForeignCommit` and `makeSourceDetails` for svn.
    """

    def makeForeignCommit(self, source_details):
        """Change the foreign tree."""
        auth = subvertpy.ra.Auth([subvertpy.ra.get_username_provider()])
        auth.set_parameter(subvertpy.AUTH_PARAM_DEFAULT_USERNAME, "lptest2")
        client = subvertpy.client.Client(auth=auth)
        client.checkout(source_details.url, 'working_tree', "HEAD")
        file = open('working_tree/newfile', 'w')
        file.write('No real content\n')
        file.close()
        client.add('working_tree/newfile')
        client.log_msg_func = lambda c: 'Add a file'
        (revnum, date, author) = client.commit(['working_tree'], recurse=True)
        # CSCVS breaks on commits without an author, so make sure there
        # is one.
        self.assertIsNot(None, author)
        self.foreign_commit_count += 1
        shutil.rmtree('working_tree')

    def makeWorkerArguments(self, branch_name, files, stacked_on_url=None):
        """Make SVN worker arguments pointing at a real SVN repo."""
        svn_server = SubversionServer(self.makeTemporaryDirectory())
        svn_server.start_server()
        self.addCleanup(svn_server.stop_server)

        svn_branch_url = svn_server.makeBranch(branch_name, files)
        svn_branch_url = svn_branch_url.replace('://localhost/', ':///')
        self.foreign_commit_count = 2
        arguments = [
            str(self.factory.getUniqueInteger()), '%s:bzr' % self.rcstype,
            svn_branch_url,
            ]
        if stacked_on_url is not None:
            arguments.append(stacked_on_url)
        return arguments


class PullingImportWorkerTests:
    """Tests for the PullingImportWorker subclasses."""

    def createBranchReference(self):
        """Create a pure branch reference that points to a branch.
        """
        branch = self.make_branch('branch')
        t = get_transport(self.get_url('.'))
        t.mkdir('reference')
        a_bzrdir = BzrDir.create(self.get_url('reference'))
        BranchReferenceFormat().initialize(a_bzrdir, target_branch=branch)
        return a_bzrdir.root_transport.base, branch.base

    def test_reject_branch_reference(self):
        # URLs that point to other branch types than that expected by the
        # import should be rejected.
        args = {'rcstype': self.rcstype}
        reference_url, target_url = self.createBranchReference()
        if self.rcstype in ('git', 'bzr-svn'):
            args['url'] = reference_url
        else:
            raise AssertionError("unexpected rcs_type %r" % self.rcstype)
        source_details = self.factory.makeCodeImportSourceDetails(**args)
        worker = self.makeImportWorker(source_details,
            opener_policy=AcceptAnythingPolicy())
        self.assertEqual(
            CodeImportWorkerExitCode.FAILURE_INVALID, worker.run())

    def test_invalid(self):
        # If there is no branch in the target URL, exit with FAILURE_INVALID
        worker = self.makeImportWorker(
            self.factory.makeCodeImportSourceDetails(
                rcstype=self.rcstype,
                url="http://localhost/path/non/existant"),
            opener_policy=AcceptAnythingPolicy())
        self.assertEqual(
            CodeImportWorkerExitCode.FAILURE_INVALID, worker.run())

    def test_forbidden(self):
        # If the branch specified is using an invalid scheme, exit with
        # FAILURE_FORBIDDEN
        worker = self.makeImportWorker(
            self.factory.makeCodeImportSourceDetails(
                rcstype=self.rcstype, url="file:///local/path"),
            opener_policy=CodeImportBranchOpenPolicy("bzr", "bzr"))
        self.assertEqual(
            CodeImportWorkerExitCode.FAILURE_FORBIDDEN, worker.run())

    def test_unsupported_feature(self):
        # If there is no branch in the target URL, exit with FAILURE_INVALID
        worker = self.makeImportWorker(self.makeSourceDetails(
            'trunk', [('bzr\\doesnt\\support\\this', 'Original contents')]),
            opener_policy=AcceptAnythingPolicy())
        self.assertEqual(
            CodeImportWorkerExitCode.FAILURE_UNSUPPORTED_FEATURE,
            worker.run())

    def test_partial(self):
        # Only config.codeimport.revisions_import_limit will be imported
        # in a given run.
        worker = self.makeImportWorker(self.makeSourceDetails(
            'trunk', [('README', 'Original contents')]),
            opener_policy=AcceptAnythingPolicy())
        self.makeForeignCommit(worker.source_details)
        self.assertTrue(self.foreign_commit_count > 1)
        import_limit = self.foreign_commit_count - 1
        self.pushConfig(
            'codeimport',
            git_revisions_import_limit=import_limit,
            svn_revisions_import_limit=import_limit)
        self.assertEqual(
            CodeImportWorkerExitCode.SUCCESS_PARTIAL, worker.run())
        self.clearCaches()
        self.assertEqual(
            CodeImportWorkerExitCode.SUCCESS, worker.run())

    def test_stacked(self):
        stacked_on = self.make_branch('stacked-on')
        source_details = self.makeSourceDetails(
            'trunk', [('README', 'Original contents')],
            stacked_on_url=stacked_on.base)
        stacked_on.fetch(Branch.open(source_details.url))
        base_rev_count = self.foreign_commit_count
        # There should only be one revision there, the other
        # one is in the stacked-on repository.
        self.addCleanup(stacked_on.lock_read().unlock)
        self.assertEqual(
            base_rev_count,
            len(stacked_on.repository.revisions.keys()))
        worker = self.makeImportWorker(
            source_details,
            opener_policy=AcceptAnythingPolicy())
        self.makeForeignCommit(source_details)
        self.assertEqual(
            CodeImportWorkerExitCode.SUCCESS, worker.run())
        branch = self.getStoredBazaarBranch(worker)
        self.assertEqual(
            base_rev_count,
            len(stacked_on.repository.revisions.keys()))
        # There should only be one revision there, the other
        # one is in the stacked-on repository.
        self.addCleanup(branch.lock_read().unlock)
        self.assertEqual(1,
             len(branch.repository.revisions.without_fallbacks().keys()))
        self.assertEqual(stacked_on.base, branch.get_stacked_on_url())


class TestGitImport(WorkerTest, TestActualImportMixin,
                    PullingImportWorkerTests):

    rcstype = 'git'

    def setUp(self):
        super(TestGitImport, self).setUp()
        self.setUpImport()

    def tearDown(self):
        self.clearCaches()
        super(TestGitImport, self).tearDown()

    def clearCaches(self):
        """Clear bzr-git's cache of sqlite connections.

        This is rather obscure: different test runs tend to re-use the same
        paths on disk, which confuses bzr-git as it keeps a cache that maps
        paths to database connections, which happily returns the connection
        that corresponds to a path that no longer exists.
        """
        from bzrlib.plugins.git.cache import mapdbs
        mapdbs().clear()

    def makeImportWorker(self, source_details, opener_policy):
        """Make a new `ImportWorker`."""
        return GitImportWorker(
            source_details, self.get_transport('import_data'),
            self.bazaar_store, logging.getLogger(),
            opener_policy=opener_policy)

    def makeForeignCommit(self, source_details, message=None, ref="HEAD"):
        """Change the foreign tree, generating exactly one commit."""
        repo = GitRepo(local_path_from_url(source_details.url))
        if message is None:
            message = self.factory.getUniqueString()
        repo.do_commit(message=message,
            committer="Joe Random Hacker <joe@example.com>", ref=ref)
        self.foreign_commit_count += 1

    def makeWorkerArguments(self, branch_name, files, stacked_on_url=None):
        """Make Git worker arguments pointing at a real Git repo."""
        repository_store = self.makeTemporaryDirectory()
        git_server = GitServer(repository_store)
        git_server.start_server()
        self.addCleanup(git_server.stop_server)

        git_server.makeRepo('source', files)
        self.foreign_commit_count = 1

        arguments = [
            str(self.factory.getUniqueInteger()), 'git:bzr',
            git_server.get_url('source'),
            ]
        if stacked_on_url is not None:
            arguments.append(stacked_on_url)
        return arguments

    def test_non_master(self):
        # non-master branches can be specified in the import URL.
        source_details = self.makeSourceDetails(
            'trunk', [('README', 'Original contents')])
        self.makeForeignCommit(source_details, ref="refs/heads/other",
            message="Message for other")
        self.makeForeignCommit(source_details, ref="refs/heads/master",
            message="Message for master")
        source_details.url = urlutils.join_segment_parameters(
                source_details.url, {"branch": "other"})
        source_transport = get_transport_from_url(source_details.url)
        self.assertEqual(
            {"branch": "other"},
            source_transport.get_segment_parameters())
        worker = self.makeImportWorker(source_details,
            opener_policy=AcceptAnythingPolicy())
        self.assertTrue(self.foreign_commit_count > 1)
        self.assertEqual(
            CodeImportWorkerExitCode.SUCCESS, worker.run())
        branch = worker.getBazaarBranch()
        lastrev = branch.repository.get_revision(branch.last_revision())
        self.assertEqual(lastrev.message, "Message for other")


class TestBzrSvnImport(WorkerTest, SubversionImportHelpers,
                       TestActualImportMixin, PullingImportWorkerTests):

    rcstype = 'bzr-svn'

    def setUp(self):
        super(TestBzrSvnImport, self).setUp()
        self.setUpImport()

    def makeImportWorker(self, source_details, opener_policy):
        """Make a new `ImportWorker`."""
        return BzrSvnImportWorker(
            source_details, self.get_transport('import_data'),
            self.bazaar_store, logging.getLogger(),
            opener_policy=opener_policy)

    def test_pushBazaarBranch_saves_bzr_svn_cache(self):
        # BzrSvnImportWorker.pushBazaarBranch saves a tarball of the bzr-svn
        # cache in the worker's ImportDataStore.
        from bzrlib.plugins.svn.cache import get_cache
        worker = self.makeImportWorker(self.makeSourceDetails(
            'trunk', [('README', 'Original contents')]),
            opener_policy=AcceptAnythingPolicy())
        uuid = subvertpy.ra.RemoteAccess(worker.source_details.url).get_uuid()
        cache_dir = get_cache(uuid).create_cache_dir()
        cache_dir_contents = os.listdir(cache_dir)
        self.assertNotEqual([], cache_dir_contents)
        opener = BranchOpener(worker._opener_policy, worker.probers)
        remote_branch = opener.open(worker.source_details.url)
        worker.pushBazaarBranch(
            self.make_branch('.'), remote_branch=remote_branch)
        worker.import_data_store.fetch('svn-cache.tar.gz')
        extract_tarball('svn-cache.tar.gz', '.')
        self.assertContentEqual(cache_dir_contents, os.listdir(uuid))

    def test_getBazaarBranch_fetches_bzr_svn_cache(self):
        # BzrSvnImportWorker.getBazaarBranch fetches the tarball of the
        # bzr-svn cache from the worker's ImportDataStore and expands it
        # into the appropriate cache directory.
        from bzrlib.plugins.svn.cache import get_cache
        worker = self.makeImportWorker(self.makeSourceDetails(
            'trunk', [('README', 'Original contents')]),
            opener_policy=AcceptAnythingPolicy())
        # Store a tarred-up cache in the store.
        content = self.factory.getUniqueString()
        uuid = str(uuid4())
        os.makedirs(os.path.join('cache', uuid))
        with open(os.path.join('cache', uuid, 'svn-cache'), 'w') as cache_file:
            cache_file.write(content)
        create_tarball('cache', 'svn-cache.tar.gz', filenames=[uuid])
        worker.import_data_store.put('svn-cache.tar.gz')
        # Make sure there's a Bazaar branch in the branch store.
        branch = self.make_branch('branch')
        ToBzrImportWorker.pushBazaarBranch(worker, branch)
        # Finally, fetching the tree gets the cache too.
        worker.getBazaarBranch()
        cache_dir = get_cache(uuid).create_cache_dir()
        with open(os.path.join(cache_dir, 'svn-cache')) as cache_file:
            self.assertEqual(content, cache_file.read())


class TestBzrImport(WorkerTest, TestActualImportMixin,
                    PullingImportWorkerTests):

    rcstype = 'bzr'

    def setUp(self):
        super(TestBzrImport, self).setUp()
        self.setUpImport()

    def makeImportWorker(self, source_details, opener_policy):
        """Make a new `ImportWorker`."""
        return BzrImportWorker(
            source_details, self.get_transport('import_data'),
            self.bazaar_store, logging.getLogger(), opener_policy)

    def makeForeignCommit(self, source_details):
        """Change the foreign tree, generating exactly one commit."""
        branch = Branch.open(source_details.url)
        builder = BranchBuilder(branch=branch)
        builder.build_commit(message=self.factory.getUniqueString(),
            committer="Joe Random Hacker <joe@example.com>")
        self.foreign_commit_count += 1

    def makeWorkerArguments(self, branch_name, files, stacked_on_url=None):
        """Make Bzr worker arguments pointing at a real Bzr repo."""
        repository_path = self.makeTemporaryDirectory()
        bzr_server = BzrServer(repository_path)
        bzr_server.start_server()
        self.addCleanup(bzr_server.stop_server)

        bzr_server.makeRepo(files)
        self.foreign_commit_count = 1

        arguments = [
            str(self.factory.getUniqueInteger()), 'bzr:bzr',
            bzr_server.get_url(),
            ]
        if stacked_on_url is not None:
            arguments.append(stacked_on_url)
        return arguments

    def test_partial(self):
        self.skipTest(
            "Partial fetching is not supported for native bzr branches "
            "at the moment.")

    def test_unsupported_feature(self):
        self.skipTest("All Bazaar features are supported by Bazaar.")

    def test_reject_branch_reference(self):
        # Branch references are allowed in the BzrImporter, but their URL
        # should be checked.
        reference_url, target_url = self.createBranchReference()
        source_details = self.factory.makeCodeImportSourceDetails(
            url=reference_url, rcstype='bzr')
        policy = _BlacklistPolicy(True, [target_url])
        worker = self.makeImportWorker(source_details, opener_policy=policy)
        self.assertEqual(
            CodeImportWorkerExitCode.FAILURE_FORBIDDEN, worker.run())

    def test_support_branch_reference(self):
        # Branch references are allowed in the BzrImporter.
        reference_url, target_url = self.createBranchReference()
        target_branch = Branch.open(target_url)
        builder = BranchBuilder(branch=target_branch)
        builder.build_commit(message=self.factory.getUniqueString(),
            committer="Some Random Hacker <jane@example.com>")
        source_details = self.factory.makeCodeImportSourceDetails(
            url=reference_url, rcstype='bzr')
        worker = self.makeImportWorker(source_details,
            opener_policy=AcceptAnythingPolicy())
        self.assertEqual(
            CodeImportWorkerExitCode.SUCCESS, worker.run())
        branch = self.getStoredBazaarBranch(worker)
        self.assertEqual(1, branch.revno())
        self.assertEqual(
            "Some Random Hacker <jane@example.com>",
            branch.repository.get_revision(branch.last_revision()).committer)


class CodeImportBranchOpenPolicyTests(TestCase):

    def setUp(self):
        super(CodeImportBranchOpenPolicyTests, self).setUp()
        self.policy = CodeImportBranchOpenPolicy("bzr", "bzr")

    def test_follows_references(self):
        self.assertEqual(True, self.policy.should_follow_references())

    def assertBadUrl(self, url):
        self.assertRaises(BadUrl, self.policy.check_one_url, url)

    def assertGoodUrl(self, url):
        self.policy.check_one_url(url)

    def test_check_one_url(self):
        self.assertBadUrl("sftp://somehost/")
        self.assertBadUrl("/etc/passwd")
        self.assertBadUrl("file:///etc/passwd")
        self.assertBadUrl("bzr+ssh://devpad/")
        self.assertBadUrl("bzr+ssh://devpad/")
        self.assertBadUrl("unknown-scheme://devpad/")
        self.assertGoodUrl("http://svn.example/branches/trunk")
        self.assertGoodUrl("http://user:password@svn.example/branches/trunk")
        self.assertBadUrl("svn+ssh://svn.example.com/bla")
        self.assertGoodUrl("bzr://bzr.example.com/somebzrurl/")
        self.assertBadUrl("bzr://bazaar.launchpad.test/example")

    def test_check_one_url_git_to_bzr(self):
        self.policy = CodeImportBranchOpenPolicy("git", "bzr")
        self.assertBadUrl("/etc/passwd")
        self.assertBadUrl("file:///etc/passwd")
        self.assertBadUrl("unknown-scheme://devpad/")
        self.assertGoodUrl("git://git.example.com/repo")
        self.assertGoodUrl("git://git.launchpad.test/example")

    def test_check_one_url_git_to_git(self):
        self.policy = CodeImportBranchOpenPolicy("git", "git")
        self.assertBadUrl("/etc/passwd")
        self.assertBadUrl("file:///etc/passwd")
        self.assertBadUrl("unknown-scheme://devpad/")
        self.assertGoodUrl("git://git.example.com/repo")
        self.assertBadUrl("git://git.launchpad.test/example")


class RedirectTests(http_utils.TestCaseWithRedirectedWebserver, TestCase):

    layer = ForeignBranchPluginLayer

    def setUp(self):
        http_utils.TestCaseWithRedirectedWebserver.setUp(self)
        self.disable_directory_isolation()
        BranchOpener.install_hook()
        tree = self.make_branch_and_tree('.')
        self.revid = tree.commit("A commit")
        self.bazaar_store = BazaarBranchStore(
            self.get_transport('bazaar_store'))

    def makeImportWorker(self, url, opener_policy):
        """Make a new `ImportWorker`."""
        source_details = self.factory.makeCodeImportSourceDetails(
            rcstype='bzr', url=url)
        return BzrImportWorker(
            source_details, self.get_transport('import_data'),
            self.bazaar_store, logging.getLogger(), opener_policy)

    def test_follow_redirect(self):
        worker = self.makeImportWorker(
            self.get_old_url(), AcceptAnythingPolicy())
        self.assertEqual(
            CodeImportWorkerExitCode.SUCCESS, worker.run())
        branch_url = self.bazaar_store._getMirrorURL(
            worker.source_details.target_id)
        branch = Branch.open(branch_url)
        self.assertEqual(self.revid, branch.last_revision())

    def test_redirect_to_forbidden_url(self):
        class NewUrlBlacklistPolicy(BranchOpenPolicy):

            def __init__(self, new_url):
                self.new_url = new_url

            def should_follow_references(self):
                return True

            def check_one_url(self, url):
                if url.startswith(self.new_url):
                    raise BadUrl(url)

            def transform_fallback_location(self, branch, url):
                return urlutils.join(branch.base, url), False

        policy = NewUrlBlacklistPolicy(self.get_new_url())
        worker = self.makeImportWorker(self.get_old_url(), policy)
        self.assertEqual(
            CodeImportWorkerExitCode.FAILURE_FORBIDDEN, worker.run())

    def test_too_many_redirects(self):
        # Make the server redirect to itself
        self.old_server = http_utils.HTTPServerRedirecting(
            protocol_version=self._protocol_version)
        self.old_server.redirect_to(self.old_server.host,
            self.old_server.port)
        self.old_server._url_protocol = self._url_protocol
        self.old_server.start_server()
        try:
            worker = self.makeImportWorker(
                self.old_server.get_url(), AcceptAnythingPolicy())
        finally:
            self.old_server.stop_server()
        self.assertEqual(
            CodeImportWorkerExitCode.FAILURE_INVALID, worker.run())
