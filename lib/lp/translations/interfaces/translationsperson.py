# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# pylint: disable-msg=E0213

__metaclass__ = type
__all__ = [
    'ITranslationsPerson',
    ]

from zope.interface import Attribute, Interface
from zope.schema import Bool

from canonical.launchpad import _


class ITranslationsPerson(Interface):
    """Translation-related properties of a person."""

    translatable_languages = Attribute(
        _('Languages this person knows, apart from English'))

    translation_history = Attribute(
        "The set of POFileTranslator objects that represent work done "
        "by this translator.")

    translation_groups = Attribute(
        "The set of TranslationGroup objects this person is a member of.")

    translators = Attribute(
        "The set of Translator objects this person is a member of.")

    translations_relicensing_agreement = Bool(
        title=_("Whether person agrees to relicense their translations"),
        readonly=False)

    def getReviewableTranslationFiles(no_older_than=None):
        """List `POFile`s this person should be able to review.

        These are translations that this person has worked on in the
        (relatively recent) past and is a reviewer for.

        :param no_older_than: Optional cutoff date.  Translations that
            this person hasn't contributed to since this date will be
            ignored.
        :return: a sequence of `POFile`s ordered by age of oldest
            unreviewed `TranslationMessage` (oldest first).
        """

    def suggestReviewableTranslationFiles(maximum):
        """Suggest `POFile`s this person could review.

        Unlike `getReviewableTranslationFiles`, this method looks for
        arbitrary translations that the person has not worked on in the
        recent past.

        :param maximum: Maximum number of `POFile`s to return.
        """
