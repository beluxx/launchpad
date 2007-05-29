# Copyright 2004-2007 Canonical Ltd.  All rights reserved.

"""Tests for the Launchpad Bazaar smart server plugin.

These tests cribbed from bzrlib/tests/blackbox/test_serve.py from Bazaar 0.16.
"""

__metaclass__ = type

import os
import signal
import shutil
import unittest

import bzrlib
from bzrlib import errors
from bzrlib.commands import get_cmd_object
from bzrlib.smart import medium
from bzrlib.tests import TestCaseInTempDir
from bzrlib.transport import get_transport, remote

from twisted.enterprise.adbapi import ConnectionPool
from twisted.internet import defer
from canonical.tests.test_twisted import TwistedTestCase

from canonical.codehosting import plugins
from canonical.codehosting.plugins import lpserve
from canonical.codehosting.tests.test_acceptance import deferToThread
from canonical.config import config
from canonical.launchpad.daemons.authserver import AuthserverService
from canonical.testing import TwistedLayer, BzrlibLayer


ROCKETFUEL_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(bzrlib.__file__)))


class TwistedBzrlibLayer(TwistedLayer, BzrlibLayer):
    """Use the Twisted reactor and Bazaar's temporary directory logic."""


class TestLaunchpadServerCommand(TwistedTestCase, TestCaseInTempDir):

    layer = TwistedBzrlibLayer

    def assertInetServerShutsdownCleanly(self, process):
        """Shutdown the server process looking for errors."""
        # Shutdown the server: the server should shut down when it cannot read
        # from stdin anymore.
        process.stdin.close()
        # Hide stdin from the subprocess module, so it won't fail to close it.
        process.stdin = None
        result = self.finish_bzr_subprocess(process, retcode=0)
        self.assertEqual('', result[0])
        self.assertEqual('', result[1])

    def assertServerFinishesCleanly(self, process):
        """Shutdown the bzr serve instance process looking for errors."""
        # Shutdown the server
        result = self.finish_bzr_subprocess(process, retcode=3,
                                            send_signal=signal.SIGINT)
        self.assertEqual('', result[0])
        self.assertEqual('bzr: interrupted\n', result[1])

    def make_empty_directory(self, directory, mode=0700):
        if os.path.isdir(directory):
            shutil.rmtree(directory)
        os.makedirs(directory, mode)

    def start_server_inet(self, user_id, extra_options=()):
        """Start a bzr server subprocess using the --inet option.

        :param extra_options: extra options to give the server.
        :return: a tuple with the bzr process handle for passing to
            finish_bzr_subprocess, a client for the server, and a transport.
        """
        # Serve from the current directory
        args = ['lp-serve', '--inet']
        args.extend(extra_options)
        args.extend([user_id])
        process = self.start_bzr_subprocess(args, skip_if_plan_to_signal=True,
                                            allow_plugins=True)

        # Connect to the server
        # We use this url because while this is no valid URL to connect to this
        # server instance, the transport needs a URL.
        client_medium = medium.SmartSimplePipesClientMedium(
            process.stdout, process.stdin)
        transport = remote.RemoteTransport(
            'bzr://localhost/', medium=client_medium)
        return process, transport

    def start_server_port(self, user_id, extra_options=()):
        """Start a bzr server subprocess.

         :param extra_options: extra options to give the server.
        :return: a tuple with the bzr process handle for passing to
            finish_bzr_subprocess, and the base url for the server.
        """
        # Serve from the current directory
        args = ['lp-serve', '--port', 'localhost:0']
        args.extend(extra_options)
        args.extend([user_id])
        process = self.start_bzr_subprocess(args, skip_if_plan_to_signal=True,
                                            allow_plugins=True)
        port_line = process.stdout.readline()
        prefix = 'listening on port: '
        self.assertStartsWith(port_line, prefix)
        port = int(port_line[len(prefix):])
        return (process, 'bzr://localhost:%d/' % port)

    def start_bzr_subprocess(self, process_args,
                             skip_if_plan_to_signal=False,
                             working_dir=None,
                             allow_plugins=False):
        env_changes = {'BZR_PLUGIN_PATH': os.path.dirname(plugins.__file__)}
        return TestCaseInTempDir.start_bzr_subprocess(
            self,
            process_args,
            env_changes=env_changes,
            skip_if_plan_to_signal=skip_if_plan_to_signal,
            working_dir=working_dir,
            allow_plugins=allow_plugins)

    def get_bzr_path(self):
        bzr_path = ROCKETFUEL_ROOT + '/sourcecode/bzr/bzr'
        assert os.path.isfile(bzr_path), "Bad Rocketfuel. Couldn't find bzr."
        return bzr_path

    def setUp(self):
        TestCaseInTempDir.setUp(self)
        # Work around bug in Twisted that prevents closing connection pools
        # synchronously.
        # See http://twistedmatrix.com/trac/ticket/2680
        ConnectionPool.shutdownID = None
        self.make_empty_directory(config.codehosting.branches_root)
        authserver = AuthserverService()
        authserver.startService()
        self.addCleanup(authserver.stopService)

    def test_command_registered(self):
        # The 'lp-serve' command object is registered as soon as the plugin is
        # imported.
        self.assertIsInstance(
            get_cmd_object('lp-serve'), lpserve.cmd_launchpad_server)

    @deferToThread
    def _test_bzr_serve_port_readonly(self):
        # When the server is started read only, attempts to write data are
        # rejected as 'TransportNotPossible'.
        #
        # This tests the 'listening on a port' code path.
        process, url = self.start_server_port('sabdfl', ['--read-only'])
        transport = get_transport(url)
        self.assertRaises(errors.TransportNotPossible,
                          transport.mkdir, '~sabdfl/+junk/new-branch')
        self.assertServerFinishesCleanly(process)

    def test_bzr_serve_port_readonly(self):
        return self._test_bzr_serve_port_readonly()

    @deferToThread
    def _test_bzr_serve_inet_readonly(self):
        # When the server is started read only, attempts to write data are
        # rejected as 'TransportNotPossible'.
        #
        # This tests the 'listening on stdio' code path.
        process, transport = self.start_server_inet('sabdfl', ['--read-only'])
        self.assertRaises(errors.TransportNotPossible,
                          transport.mkdir, '~sabdfl/+junk/new-branch')
        self.assertInetServerShutsdownCleanly(process)

    def test_bzr_serve_inet_readonly(self):
        return self._test_bzr_serve_inet_readonly()

    @deferToThread
    def _test_bzr_serve_inet_readwrite(self):
        # When the server is started normally (i.e. allowing writes), we can
        # use a transport pointing at the server to make directories, create
        # files and so forth. These operations are then translated to the local
        # file system.
        local_transport = get_transport(config.codehosting.branches_root)
        old_file_list = list(local_transport.iter_files_recursive())
        self.assertEqual([], old_file_list)

        process, transport = self.start_server_inet('sabdfl')
        transport.mkdir('~sabdfl/+junk/new-branch')
        transport.mkdir('~sabdfl/+junk/new-branch/.bzr')
        transport.put_bytes('~sabdfl/+junk/new-branch/.bzr/README', 'Hello')

        new_file_list = list(local_transport.iter_files_recursive())
        self.assertEqual(1, len(new_file_list))
        self.assertTrue(new_file_list[0].endswith('.bzr/README'),
                        "Expected .bzr/README, got %r" % (new_file_list[0]))

        self.assertInetServerShutsdownCleanly(process)

    def test_bzr_serve_inet_readwrite(self):
        return self._test_bzr_serve_inet_readwrite()


def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)
