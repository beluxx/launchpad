# Copyright 2019-2021 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Message revision history."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type
__all__ = [
    'MessageRevision'
    ]

import pytz
from storm.locals import (
    DateTime,
    Int,
    Reference,
    Unicode,
    )
from zope.interface import implementer

from lp.services.database.interfaces import IStore
from lp.services.database.stormbase import StormBase
from lp.services.messages.interfaces.messagerevision import IMessageRevision
from lp.services.utils import utc_now


@implementer(IMessageRevision)
class MessageRevision(StormBase):
    """A historical revision of a IMessage."""

    __storm_table__ = 'MessageRevision'

    id = Int(primary=True)

    message_id = Int(name='message', allow_none=False)
    message = Reference(message_id, 'Message.id')

    content = Unicode(name="content", allow_none=False)

    date_created = DateTime(
        name="date_created", tzinfo=pytz.UTC, allow_none=False)
    date_deleted = DateTime(
        name="date_deleted", tzinfo=pytz.UTC, allow_none=True)

    def __init__(self, message, content, date_created, date_deleted=None):
        self.message = message
        self.content = content
        self.date_created = date_created
        self.date_deleted = date_deleted

    @property
    def message_implementation(self):
        from lp.bugs.model.bugmessage import BugMessage
        from lp.code.model.codereviewcomment import CodeReviewComment
        from lp.answers.model.questionmessage import QuestionMessage

        store = IStore(self)
        (identifier, ) = store.execute("""
            SELECT 'bug' FROM BugMessage WHERE message = %s
            UNION
            SELECT 'question' FROM QuestionMessage WHERE message = %s
            UNION
            SELECT 'mp' FROM CodeReviewMessage WHERE message = %s;
        """, params=[self.message_id] * 3).get_one()
        id_to_class = {
            "bug": BugMessage,
            "question": QuestionMessage,
            "mp": CodeReviewComment}
        klass = id_to_class[identifier]
        return store.find(klass, klass.message == self.message_id).one()

    def destroySelf(self):
        self.date_deleted = utc_now()
