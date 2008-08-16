# Copyright 2007 Canonical Ltd.  All rights reserved.

"""Watch a log file and wait until it has grown in size."""

__metaclass__ = type
__all__ = [
    'LogWatcher',
    'MHonArcWatcher',
    'SMTPDWatcher',
    'VetteWatcher',
    'XMLRPCWatcher',
    ]


import os
import time
import datetime

# pylint: disable-msg=F0401
from Mailman.mm_cfg import LOG_DIR

try:
    # Python 2.5
    SEEK_END = os.SEEK_END
except AttributeError:
    # Python 2.4
    SEEK_END = 2


LINES_TO_CAPTURE = 50
LOG_GROWTH_WAIT_INTERVAL = datetime.timedelta(seconds=5)
SECONDS_TO_SNOOZE = 0.1
Empty = object()
NL = '\n'


class LogWatcher:
    """Watch logs/xmlrpc and wait until a pattern has been seen.

    You MUST open the LogWatcher before any data you're interested in could
    get written to the log.

    This class (and its subclasses) are how we ensure synchronization among
    the various independent processes involved in the tests.  Without this
    synchronization, our tests are subject to highly unstable race conditions.

    The various wait*() methods in the subclasses are called to wait for an
    expected landmark written to a log file.  For example, if we're waiting
    for the delivery of an email message with the Message-ID: <zulu>, we never
    know exactly when the other process will write this.  We /do/ know that
    once that landmark is written, the state we expect to test will exist.

    This is safe because we have only one process writing to any particular
    log file, and that process is single threaded.  Further, the messages it
    writes will always be in a predictable order, so this is a reliable
    synchronization point.

    Set `expecting_timeout` to True on the watcher instance just before a
    wait*() call if you expect a time out.  This will suppress any logging
    information normally printed when a time out occurs.  `expecting_timeout`
    is automatically reset to False after the time out occurs.
    """
    FILENAME = None
    expecting_timeout = False

    def __init__(self):
        self._log_path = os.path.join(LOG_DIR, self.FILENAME)
        log_file = open(self._log_path, 'a+')
        try:
            print >> log_file, datetime.datetime.now(), 'LogWatcher created'
        finally:
            log_file.close()
        self._log_file = open(self._log_path)
        self._log_file.seek(0, SEEK_END)
        self._line_cache = []
        self.last_lines_read = []

    @property
    def lines(self):
        # Keep a cache of the lines read from the file.
        while True:
            if len(self._line_cache) == 0:
                # The cache is empty, so first return a special marker telling
                # the consumer that there are no more lines available.
                yield Empty
                # Read all newly available lines from the file, between the
                # current file position and the current EOF.
                self._line_cache = self._log_file.readlines()
            else:
                yield self._line_cache.pop(0)

    def wait(self, landmark):
        """Wait until the landmark string has been seen.

        'landmark' must appear on a single line.  Comparison is done with 'in'
        on each line of the file.
        """
        until = datetime.datetime.now() + LOG_GROWTH_WAIT_INTERVAL
        for line in self.lines:
            if line is Empty:
                # There's nothing in the file for us.  See if we timed out and
                # if not, sleep for a little while.
                if datetime.datetime.now() > until:
                    if not self.expecting_timeout:
                        print NL.join(self.last_lines_read)
                    # Resetting expectations so you don't have to.
                    self.expecting_timeout = False
                    return 'Timed out'
                time.sleep(SECONDS_TO_SNOOZE)
            elif landmark in line:
                # Return None on success for doctest convenience.
                self.last_lines_read.append(line)
                del self.last_lines_read[0:-LINES_TO_CAPTURE]
                return None
            else:
                # This line did not match our landmark.  Try again with the
                # next line, but keep a cache of the last 10 lines read so
                # that a timeout will be able to provide more debugging.
                self.last_lines_read.append(line)
                del self.last_lines_read[0:-LINES_TO_CAPTURE]

    def close(self):
        self._log_file.close()


class XMLRPCWatcher(LogWatcher):
    """Watch logs/xmlrpc."""

    FILENAME = 'xmlrpc'

    def wait_for_create(self, team_name):
        """Wait for the list creation message."""
        return self.wait('[%s] create/reactivate: success' % team_name)

    def wait_for_resynchronization(self, team_name):
        return self.wait('[%s] resynchronize: success' % team_name)

    def wait_for_deactivation(self, team_name):
        return self.wait('[%s] deactivate: success' % team_name)

    wait_for_reactivation = wait_for_create

    def wait_for_modification(self, team_name):
        return self.wait('[%s] modify: success' % team_name)

    def wait_for_discard(self, message_id):
        return self.wait('Discarded: <%s>' % message_id)

    def wait_for_reject(self, message_id):
        return self.wait('Rejected: <%s>' % message_id)

    def wait_for_approval(self, message_id):
        return self.wait('Approved: <%s>' % message_id)


class SMTPDWatcher(LogWatcher):
    """Watch logs/smtpd."""

    FILENAME = 'smtpd'

    def wait_for_mbox_delivery(self, message_id):
        return self.wait('msgid: <%s>' % message_id)

    def wait_for_list_traffic(self, team_name):
        return self.wait('to: %s@lists.launchpad.dev' % team_name)

    def wait_for_personal_traffic(self, address):
        return self.wait('to: ' + address)


class MHonArcWatcher(LogWatcher):
    """Watch logs/mhonarc."""

    FILENAME = 'mhonarc'

    def wait_for_message_number(self, n):
        return self.wait('%s total' % n)


class VetteWatcher(LogWatcher):
    """Watch logs/vette."""

    FILENAME = 'vette'

    def wait_for_discard(self, message_id):
        return self.wait('Message discarded, msgid: <%s>' % message_id)

    def wait_for_hold(self, message_id):
        return self.wait(
            'Holding message for LP approval: <%s>' % message_id)


class QrunnerWatcher(LogWatcher):
    """Watch logs/qrunner."""

    FILENAME = 'qrunner'

    def _wait_for_runner_startup(self):
        return self.wait('qrunner started.')

    def wait_for_restart(self):
        # Wait for the master qrunner to start 6 runners, in no deterministic
        # order: ArchRunner, BounceRunner, RetryRunner, VirginRunner,
        # IncomingRunner, OutgoingRunner.
        for runner in range(6):
            result = self.wait_for_runner_startup()
            if result is not None:
                return result
        return None

    def _wait_for_runner_exit(self):
        return self.wait('Master qrunner detected subprocess exit')

    def wait_for_shutdown(self):
        # Wait for the master qrunner to detect 6 runner exits, in no
        # deterministic order: ArchRunner, BounceRunner, RetryRunner,
        # VirginRunner, IncomingRunner, OutgoingRunner.
        for runner in range(6):
            result = self.wait_for_runner_exit()
            if result is not None:
                return result
        return None
