# Copyright 2009-2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""FAQ document models."""

__metaclass__ = type

__all__ = [
    'FAQ',
    'FAQSearch',
    'FAQSet',
    ]

from lazr.lifecycle.event import ObjectCreatedEvent
import six
from sqlobject import (
    ForeignKey,
    SQLMultipleJoin,
    SQLObjectNotFound,
    StringCol,
    )
from storm.expr import And
from storm.references import ReferenceSet
from zope.event import notify
from zope.interface import implementer

from lp.answers.interfaces.faq import (
    CannotDeleteFAQ,
    IFAQ,
    IFAQSet,
    )
from lp.answers.interfaces.faqcollection import FAQSort
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.person import (
    IPerson,
    validate_public_person,
    )
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.services.database.constants import DEFAULT
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.nl_search import nl_phrase_search
from lp.services.database.sqlbase import (
    quote,
    SQLBase,
    sqlvalues,
    )
from lp.services.database.stormexpr import (
    fti_search,
    rank_by_fti,
    )


@implementer(IFAQ)
class FAQ(SQLBase):
    """See `IFAQ`."""

    _table = 'FAQ'
    _defaultOrder = ['date_created', 'id']

    owner = ForeignKey(
        dbName='owner', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)

    title = StringCol(notNull=True)

    keywords = StringCol(dbName="tags", notNull=False, default=None)

    content = StringCol(notNull=False, default=None)

    date_created = UtcDateTimeCol(notNull=True, default=DEFAULT)

    last_updated_by = ForeignKey(
        dbName='last_updated_by', foreignKey='Person',
        storm_validator=validate_public_person, notNull=False,
        default=None)

    date_last_updated = UtcDateTimeCol(notNull=False, default=None)

    product = ForeignKey(
        dbName='product', foreignKey='Product', notNull=False, default=None)

    distribution = ForeignKey(
        dbName='distribution', foreignKey='Distribution', notNull=False,
        default=None)

    related_questions = ReferenceSet(
        'id', 'Question.faq_id', order_by=('Question.datecreated'))

    @property
    def target(self):
        """See `IFAQ`."""
        if self.product:
            return self.product
        else:
            return self.distribution

    def destroySelf(self):
        if not self.related_questions.is_empty():
            raise CannotDeleteFAQ(
               "Cannot delete FAQ: questions must be unlinked first.")
        super(FAQ, self).destroySelf()

    @staticmethod
    def new(owner, title, content, keywords=keywords, date_created=None,
            product=None, distribution=None):
        """Factory method to create a new FAQ.

        Ensure that only one of product or distribution is given.
        """
        if not IPerson.providedBy(owner):
            raise AssertionError(
                'owner parameter should be an IPerson, not %s' % type(owner))
        if product is not None and distribution is not None:
            raise AssertionError(
                "only one of product or distribution should be provided")
        if product is None and distribution is None:
            raise AssertionError("product or distribution must be provided")
        if date_created is None:
            date_created = DEFAULT
        faq = FAQ(
            owner=owner, title=title, content=content, keywords=keywords,
            date_created=date_created, product=product,
            distribution=distribution)
        notify(ObjectCreatedEvent(faq))
        return faq

    @staticmethod
    def findSimilar(summary, product=None, distribution=None):
        """Return the FAQs similar to summary.

        See `IFAQTarget.findSimilarFAQs` for details.
        """
        assert not (product and distribution), (
            'only one of product or distribution should be provided')
        if product:
            target_constraint = (FAQ.product == product)
        elif distribution:
            target_constraint = (FAQ.distribution == distribution)
        else:
            raise AssertionError('must provide product or distribution')

        phrases = nl_phrase_search(summary, FAQ, [target_constraint])
        if not phrases:
            # No useful words to search on in that summary.
            return FAQ.select('1 = 2')

        return FAQ.select(
            And(target_constraint, fti_search(FAQ, phrases, ftq=False)),
            orderBy=[
                rank_by_fti(FAQ, phrases, ftq=False), "-FAQ.date_created"])

    @staticmethod
    def getForTarget(id, target):
        """Return the FAQ with the requested id.

        When target is not None, the target will be checked to make sure
        that the FAQ is in the expected target or return None otherwise.
        """
        try:
            faq = FAQ.get(id)
            if target is None or target == faq.target:
                return faq
            else:
                return None
        except SQLObjectNotFound:
            return None


class FAQSearch:
    """Object that encapsulates a FAQ search.

    It is used to implement the `IFAQCollection`.searchFAQs() method.
    """
    search_text = None
    owner = None
    sort = None
    product = None
    distribution = None
    projectgroup = None

    def __init__(self, search_text=None, owner=None, sort=None, product=None,
                 distribution=None, projectgroup=None):
        """Initialize a new FAQ search.

        See `IFAQCollection`.searchFAQs for the basic parameters description.
        Additional parameters:
        :param product: The product in which to search for FAQs.
        :param distribution: The distribution in which to search for FAQs.
        :param projectgroup: The project group in which to search for FAQs.
        """
        if search_text is not None:
            assert isinstance(search_text, six.string_types), (
                'search_text should be a string, not %s' % type(search_text))
            self.search_text = search_text

        if owner is not None:
            assert IPerson.providedBy(owner), (
                'owner should be an IPerson, not %s' % type(owner))
            self.owner = owner

        if sort is not None:
            assert sort in FAQSort.items, (
                'sort should be an item from FAQSort, not %s' % type(sort))
            self.sort = sort

        if product is not None:
            assert IProduct.providedBy(product), (
                'product should be an IProduct, not %s' % type(product))
            assert distribution is None and projectgroup is None, (
                'can only use one of product, distribution, or projectgroup')
            self.product = product

        if distribution is not None:
            assert IDistribution.providedBy(distribution), (
                'distribution should be an IDistribution, %s' %
                type(distribution))
            assert product is None and projectgroup is None, (
                'can only use one of product, distribution, or projectgroup')
            self.distribution = distribution

        if projectgroup is not None:
            assert IProjectGroup.providedBy(projectgroup), (
                'projectgroup should be an IProjectGroup, not %s' %
                type(projectgroup))
            assert product is None and distribution is None, (
                'can only use one of product, distribution, or projectgroup')
            self.projectgroup = projectgroup

    def getResults(self):
        """Return the FAQs matching this search."""
        return FAQ.select(
            self.getConstraints(),
            clauseTables=self.getClauseTables(),
            orderBy=self.getOrderByClause())

    def getConstraints(self):
        """Return the constraints to use by this search."""
        constraints = []

        if self.search_text:
            constraints.append('FAQ.fti @@ ftq(%s)' % quote(self.search_text))

        if self.owner:
            constraints.append('FAQ.owner = %s' % sqlvalues(self.owner))

        if self.product:
            constraints.append('FAQ.product = %s' % sqlvalues(self.product))

        if self.distribution:
            constraints.append(
                'FAQ.distribution = %s' % sqlvalues(self.distribution))

        if self.projectgroup:
            constraints.append(
                'FAQ.product = Product.id AND Product.project = %s' % (
                    sqlvalues(self.projectgroup)))

        return '\n AND '.join(constraints)

    def getClauseTables(self):
        """Return the tables that should be added to the FROM clause."""
        if self.projectgroup:
            return ['Product']
        else:
            return []

    def getOrderByClause(self):
        """Return the ORDER BY clause to sort the results."""
        sort = self.sort
        if sort is None:
            if self.search_text is not None:
                sort = FAQSort.RELEVANCY
            else:
                sort = FAQSort.NEWEST_FIRST
        if sort is FAQSort.NEWEST_FIRST:
            return "-FAQ.date_created"
        elif sort is FAQSort.OLDEST_FIRST:
            return "FAQ.date_created"
        elif sort is FAQSort.RELEVANCY:
            if self.search_text:
                return [
                    rank_by_fti(FAQ, self.search_text), "-FAQ.date_created"]
            else:
                return "-FAQ.date_created"
        else:
            raise AssertionError("Unknown FAQSort value: %r" % sort)


@implementer(IFAQSet)
class FAQSet:
    """See `IFAQSet`."""

    def getFAQ(self, id):
        """See `IFAQSet`."""
        return FAQ.getForTarget(id, None)

    def searchFAQs(self, search_text=None, owner=None, sort=None):
        """See `IFAQSet`."""
        return FAQSearch(
            search_text=search_text, owner=owner, sort=sort).getResults()
