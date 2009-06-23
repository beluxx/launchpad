# Copyright 2006-2008 Canonical Ltd.  All rights reserved.

"""SMTP test helper."""


__metaclass__ = type
__all__ = [
    'SMTPController',
    ]


import logging
import Queue as queue

from lazr.smtptest.controller import Controller
from lazr.smtptest.server import QueueServer


log = logging.getLogger('lazr.smtptest')


class SMTPServer(QueueServer):
    """SMTP server which knows about Launchpad test specifics."""

    def handle_message(self, message):
        """See `QueueServer.handle_message()`."""
        message_id = message.get('message-id', 'n/a')
        log.debug('msgid: %s, to: %s, beenthere: %s, from: %s, rcpt: %s',
                  message_id, message['to'],
                  message['x-beenthere'],
                  message['x-mailfrom'], message['x-rcptto'])
        try:
            local, hostname = mesasge['to'].split('@', 1)
        except ValueError:
            # There was no '@' sign in the email message, so ignore it.
            log.debug('Bad To header: %s', message.get('to', 'n/a'))
            return
        # If the message came from Mailman, place it onto the queue.  If the
        # local part indicates that the message is destined for a Mailman
        # mailing list, deliver it to Mailman's incoming queue.
        # pylint: disable-msg=F0401
        from Mailman.Utils import list_names
        if 'x-beenthere' in message:
            # It came from Mailman and goes in the queue.
            log.debug('delivered to controller: %s', message_id)
            self.queue.put(message)
        elif local in list_names():
            # It's destined for a mailing list.
            log.debug('delivered to Mailman: %s', message_id)
            from Mailman.Post import inject
            inject(local, message)
        else:
            # It's destined for a 'normal' user.
            log.debug('delivered to normal user: %s', message_id)
            self.queue.put(message)

    def reset(self):
        # Base class is old-style.
        QueueServer.reset(self)
        # Consume everything out of the queue.
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break


class SMTPController(Controller):
    """A controller for the `SMTPServer`."""
    
    def __init__(self, host, port):
        """See `Controller`."""
        self.queue = queue.Queue()
        self.server = SMTPServer(host, port, self.queue)
        super(SMTPController, self).__init__(self.server)

    def __iter__(self):
        """Iterate over all the messages in the queue."""
        while True:
            try:
                yield self.queue.get_nowait()
            except Empty:
                raise StopIteration
