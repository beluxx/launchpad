# Copyright 2004-2007 Canonical Ltd.  All rights reserved.

__metaclass__ = type

__all__ = [
    'TicketMessage',
    ]

from email.Utils import make_msgid

from zope.interface import implements

from sqlobject import ForeignKey

from canonical.launchpad import _

from canonical.database.sqlbase import SQLBase
from canonical.database.enumcol import EnumCol

from canonical.launchpad.database.message import Message, MessageChunk
from canonical.launchpad.interfaces import IMessage, ITicketMessage

from canonical.lp import decorates
from canonical.lp.dbschema import QuestionAction, QuestionStatus


class TicketMessage(SQLBase):
    """A table linking tickets and messages."""

    implements(ITicketMessage)

    decorates(IMessage, context='message')

    _table = 'TicketMessage'

    ticket = ForeignKey(dbName='ticket', foreignKey='Ticket', notNull=True)
    message = ForeignKey(dbName='message', foreignKey='Message', notNull=True)

    action = EnumCol(
        schema=QuestionAction, notNull=True, default=QuestionAction.COMMENT)

    new_status = EnumCol(
        schema=QuestionStatus, notNull=True, default=QuestionStatus.OPEN)
