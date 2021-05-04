# Copyright 2019-2021 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Message revision history."""

from __future__ import absolute_import, print_function, unicode_literals

__all__ = [
    'IMessageRevision'
    ]

from lazr.restful.declarations import (
    exported,
    exported_as_webservice_entry,
    )
from lazr.restful.fields import Reference
from zope.interface import Interface
from zope.schema import (
    Datetime,
    Int,
    Text,
    )

from lp import _
from lp.services.messages.interfaces.message import IMessage


@exported_as_webservice_entry(publish_web_link=False, as_of="devel")
class IMessageRevisionView(Interface):
    """IMessageRevision readable attributes."""
    id = Int(title=_("ID"), required=True, readonly=True)

    content = exported(Text(
        title=_("The message at the given revision"),
        required=False, readonly=True))

    message = Reference(
        title=_('The current message of this revision.'),
        schema=IMessage, required=True, readonly=True)

    message_implementation = Reference(
        title=_('The message implementation (BugComment, QuestionMessage or '
                'CodeReviewComment) related to this revision'),
        schema=Interface, required=True, readonly=True)

    date_created = exported(Datetime(
        title=_("The time when this message revision was created."),
        required=True, readonly=True))

    date_deleted = exported(Datetime(
        title=_("The time when this message revision was created."),
        required=False, readonly=True))


class IMessageRevisionEdit(Interface):
    """IMessageRevision editable attributes."""

    def destroySelf():
        """Logically deletes this MessageRevision."""


class IMessageRevision(IMessageRevisionView, IMessageRevisionEdit):
    """A historical revision of a IMessage."""
