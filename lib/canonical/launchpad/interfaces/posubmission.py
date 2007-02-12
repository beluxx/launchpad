# Copyright 2005-2006 Canonical Ltd.  All rights reserved.

from zope.interface import Interface, Attribute
from zope.schema import Object, Datetime, Bool

__metaclass__ = type
__all__ = [
    'IPOSubmission',
    'IPOSubmissionSet'
    ]

class IPOSubmissionSet(Interface):
    """The set of submissions we have in our database."""

    def getPOSubmissionByID(id):
        """Return the IPOsubmission with the given id or None.

        :arg id: IPOSubmission.id
        """


class IPOSubmission(Interface):
    """A submission of a translation to a PO file."""

    id = Attribute("The ID for this submission.")
    pomsgset = Attribute("The PO message set for which is this submission.")
    pluralform = Attribute("The # of pluralform that we are submitting.")
    potranslation = Attribute("The translation that was submitted.")
    datecreated = Attribute("The date we saw this submission.")
    origin = Attribute("Where the submission originally came from.")
    person = Attribute("The owner of this submission, if we have one.")
    validationstatus = Attribute(
        "The status of the validation of the translation.")

    active = Bool(
        title=("Whether this submission is active."),
        required=True)
    published = Bool(
        title=("Whether this submission is published."),
        required=True)
    reviewer = Object(
        title=u'The person who did the review and accepted current active'
              u'translation.',
        required=False, schema=IPerson)
    date_reviewed = Datetime(
        title=u'The date when this message was reviewed for last time.',
        required=False)


    def destroySelf():
        """Remove this object.

        It should not be referenced by any other object.
        """
