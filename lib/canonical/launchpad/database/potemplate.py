# Copyright 2004-2005 Canonical Ltd.  All rights reserved.

__metaclass__ = type
__all__ = ['POTemplateSubset', 'POTemplateSet', 'LanguageNotFound',
           'POTemplate']

import StringIO
import datetime

# Zope interfaces
from zope.interface import implements
from zope.exceptions import NotFoundError

# SQL imports
from sqlobject import ForeignKey, IntCol, StringCol, BoolCol
from sqlobject import MultipleJoin, SQLObjectNotFound
from canonical.database.sqlbase import \
    SQLBase, quote, flush_database_updates, sqlvalues
from canonical.database.datetimecol import UtcDateTimeCol

# canonical imports
from canonical.launchpad.interfaces import \
    IEditPOTemplate, IPOTemplateSet, IPOTemplateSubset, IRawFileData, ITeam
from canonical.launchpad.database.language import Language
from canonical.launchpad.database.potmsgset import POTMsgSet
from canonical.launchpad.database.pomsgidsighting import POMsgIDSighting
from canonical.lp.dbschema import EnumCol
from canonical.launchpad.database.potemplatename import POTemplateName
from canonical.launchpad.database.pofile import POFile
from canonical.launchpad.database.pomsgid import POMsgID
from canonical.lp.dbschema import RosettaImportStatus
from canonical.database.constants import DEFAULT, UTC_NOW
from canonical.launchpad.components.rosettastats import RosettaStats
from canonical.launchpad.components.poimport import import_po
from canonical.launchpad import helpers

from canonical.launchpad.components.poparser import (POSyntaxError,
    POInvalidInputError)

standardPOFileTopComment = ''' %(languagename)s translation for %(origin)s
 Copyright (c) %(copyright)s %(year)s
 This file is distributed under the same license as the %(origin)s package.
 FIRST AUTHOR <EMAIL@ADDRESS>, %(year)s.

'''

standardPOFileHeader = (
"Project-Id-Version: %(origin)s\n"
"Report-Msgid-Bugs-To: FULL NAME <EMAIL@ADDRESS>\n"
"POT-Creation-Date: %(templatedate)s\n"
"PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\n"
"Language-Team: %(languagename)s <%(languagecode)s@li.org>\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: 8bit\n"
"X-Rosetta-Version: 0.1\n"
"Plural-Forms: nplurals=%(nplurals)d; plural=%(pluralexpr)s\n"
)

class POTemplate(SQLBase, RosettaStats):
    implements(IEditPOTemplate, IRawFileData)

    _table = 'POTemplate'

    productrelease = ForeignKey(foreignKey='ProductRelease',
        dbName='productrelease', notNull=False, default=None)
    priority = IntCol(dbName='priority', notNull=False, default=None)
    potemplatename = ForeignKey(foreignKey='POTemplateName',
        dbName='potemplatename', notNull=True)
    description = StringCol(dbName='description', notNull=False, default=None)
    copyright = StringCol(dbName='copyright', notNull=False, default=None)
    # XXX: Why?
    #       SteveAlexander 2005-04-23
    #license = ForeignKey(foreignKey='License', dbName='license', notNull=True)
    license = IntCol(dbName='license', notNull=False, default=None)
    datecreated = UtcDateTimeCol(dbName='datecreated', default=DEFAULT)
    path = StringCol(dbName='path', notNull=False, default=None)
    iscurrent = BoolCol(dbName='iscurrent', notNull=True, default=True)
    messagecount = IntCol(dbName='messagecount', notNull=True, default=0)
    owner = ForeignKey(foreignKey='Person', dbName='owner', notNull=True)
    sourcepackagename = ForeignKey(foreignKey='SourcePackageName',
        dbName='sourcepackagename', notNull=False, default=None)
    sourcepackageversion = StringCol(dbName='sourcepackageversion',
        notNull=False, default=None)
    distrorelease = ForeignKey(foreignKey='DistroRelease',
        dbName='distrorelease', notNull=False, default=None)
    header = StringCol(dbName='header', notNull=False, default=None)
    binarypackagename = ForeignKey(foreignKey='BinaryPackageName',
        dbName='binarypackagename', notNull=False, default=None)
    languagepack = BoolCol(dbName='languagepack', notNull=True, default=False)
    filename = StringCol(dbName='filename', notNull=False, default=None)

    # joins
    pofiles = MultipleJoin('POFile', joinColumn='potemplate')

    def __len__(self):
        """Return the number of CURRENT POTMsgSets in this POTemplate."""
        return self.messageCount()

    def __iter__(self):
        """See IPOTemplate."""
        return self.getPOTMsgSets()

    def __getitem__(self, key):
        """See IPOTemplate."""
        return self.getPOTMsgSetByMsgIDText(key, onlyCurrent=True)

    # properties
    @property
    def name(self):
        """See IPOTemplate."""
        return self.potemplatename.name

    @property
    def displayname(self):
        """See IPOTemplate."""
        if self.productrelease:
            dn = '%s in %s %s' % (
                self.name,
                self.productrelease.product.displayname,
                self.productrelease.version)
        if self.distrorelease:
            dn = '%s in %s %s package "%s"' % (
                self.name,
                self.distrorelease.distribution.displayname,
                self.distrorelease.displayname,
                self.sourcepackagename.name)
        return dn

    @property
    def title(self):
        """See IPOTemplate."""
        if self.productrelease:
            title = 'Template "%s" in %s %s' % (
                self.name,
                self.productrelease.product.displayname,
                self.productrelease.version)
        if self.distrorelease:
            title = 'Template "%s" in %s %s package "%s"' % (
                self.name,
                self.distrorelease.distribution.displayname,
                self.distrorelease.displayname,
                self.sourcepackagename.name)
        return title


    @property
    def translationgroups(self):
        """See IPOTemplate."""
        ret = []
        if self.distrorelease:
            tg = self.distrorelease.distribution.translationgroup
            if tg is not None:
                ret.append(tg)
        elif self.productrelease:
            product_tg = self.productrelease.product.translationgroup
            if product_tg is not None:
                ret.append(product_tg)
            project = self.productrelease.product.project
            if project is not None:
                if project.translationgroup is not None:
                    ret.append(project.translationgroup)
        else:
            raise NotImplementedError, 'Cannot find translation groups.'
        return ret

    @property
    def translationpermission(self):
        """See IPOTemplate."""
        # in the case of a distro template, use the distro translation
        # permission settings
        if self.distrorelease:
            return self.distrorelease.distribution.translationpermission
        # for products, use the "most restrictive permission" between
        # project and product.
        elif self.productrelease:
            return self.productrelease.product.aggregatetranslationpermission

    @property
    def translationgroups(self):
        ret = []
        if self.distrorelease:
            tg = self.distrorelease.distribution.translationgroup
            if tg is not None:
                ret.append(tg)
        elif self.productrelease:
            product_tg = self.productrelease.product.translationgroup
            if product_tg is not None:
                ret.append(product_tg)
            project = self.productrelease.product.project
            if project is not None:
                if project.translationgroup is not None:
                    ret.append(project.translationgroup)
        else:
            raise NotImplementedError, 'Cannot find translation groups.'
        return ret

    @property
    def translationpermission(self):
        if self.distrorelease:
            # in the case of a distro template, use the distro translation
            # permission settings
            return self.distrorelease.distribution.translationpermission
        elif self.productrelease:
            # for products, use the "most restrictive permission" between
            # project and product.
            return self.productrelease.product.aggregatetranslationpermission

    @property
    def relatives_by_name(self):
        "See IPOTemplate"
        return POTemplate.select('''
            id <> %s AND
            potemplatename = %s
            ''' % sqlvalues (self.id, self.potemplatename.id),
            orderBy=['datecreated'])

    @property
    def relatives_by_source(self):
        "See IPOTemplate"
        if self.productrelease:
            return POTemplate.select('''
                id <> %s AND
                productrelease = %s
                ''' % sqlvalues(self.id, self.productrelease.id),
                orderBy=['id'])
        elif self.distrorelease and self.sourcepackagename:
            return POTemplate.select('''
                id <> %s AND
                distrorelease = %s AND
                sourcepackagename = %s
                ''' % sqlvalues(self.id,
                    self.distrorelease.id, self.sourcepackagename.id),
                orderBy=['id'])
        else:
            raise AssertionError('Unknown POTemplate source.')

    @property
    def language_count(self):
        return Language.select('''
            POFile.language = Language.id AND
            POFile.currentcount + POFile.rosettacount > 0 AND
            POFile.potemplate = %s
            ''' % sqlvalues(self.id),
            clauseTables=['POFile'],
            distinct=True).count()


    def getPOTMsgSetByMsgIDText(self, key, onlyCurrent=False):
        """See IPOTemplate."""
        query = 'potemplate = %s' % sqlvalues(self.id)
        if onlyCurrent:
            query += ' AND sequence > 0'

        # Find a message ID with the given text.
        try:
            pomsgid = POMsgID.byMsgid(key)
        except SQLObjectNotFound:
            raise NotFoundError(key)

        # Find a message set with the given message ID.

        result = POTMsgSet.selectOne(query +
            (' AND primemsgid = %s' % sqlvalues(pomsgid.id)))

        if result is None:
            raise NotFoundError(key)
        return result

    def getPOTMsgSetBySequence(self, key, onlyCurrent=False):
        """See IPOTemplate."""
        query = 'potemplate = %s' % sqlvalues(self.id)
        if onlyCurrent:
            query += ' AND sequence > 0'

        return POTMsgSet.select(query, orderBy='sequence')[key]

    def getPOTMsgSets(self, current=True, slice=None):
        """See IPOTemplate."""
        if current:
            # Only count the number of POTMsgSet that are current.
            results = POTMsgSet.select(
                'POTMsgSet.potemplate = %s AND POTMsgSet.sequence > 0' %
                    sqlvalues(self.id),
                orderBy='sequence')
        else:
            results = POTMsgSet.select(
                'POTMsgSet.potemplate = %s' % sqlvalues(self.id),
                orderBy='sequence')

        if slice is None:
            # Want all the output.
            for potmsgset in results:
                yield potmsgset
        else:
            # Want only a subset specified by slice.
            for potmsgset in results[slice]:
                yield potmsgset

    def getPOTMsgSetsCount(self, current=True):
        """See IPOTemplate."""
        if current:
            # Only count the number of POTMsgSet that are current
            results = POTMsgSet.select(
                'POTMsgSet.potemplate = %s AND POTMsgSet.sequence > 0' %
                    sqlvalues(self.id))
        else:
            results = POTMsgSet.select(
                'POTMsgSet.potemplate = %s' % sqlvalues(self.id))

        return results.count()

    def getPOTMsgSetByID(self, id):
        """See IPOTemplate."""
        return POTMsgSet.selectOne(
            "POTMsgSet.potemplate = %d AND POTMsgSet.id = %d" % (self.id, id))

    def languages(self):
        """This returns the set of languages for which we have
        POFiles for this POTemplate.

        NOTE that variants are simply ignored, if we have three variants for
        en_GB we will simply return the one with variant=NULL.
        """
        return Language.select("POFile.language = Language.id AND "
                               "POFile.potemplate = %d AND "
                               "POFile.variant IS NULL" % self.id,
                               clauseTables=['POFile', 'Language'],
                               distinct=True
                               )

    def poFilesToImport(self):
        for pofile in self.pofiles:
            if pofile.rawimportstatus == RosettaImportStatus.PENDING:
                yield pofile

    def getPOFileByLang(self, language_code, variant=None):
        if variant is None:
            variantspec = 'IS NULL'
        elif isinstance(variant, unicode):
            variantspec = (u'= %s' % quote(variant))
        else:
            raise TypeError('Variant must be None or unicode.')

        pofile = POFile.selectOne("""
            POFile.potemplate = %d AND
            POFile.language = Language.id AND
            POFile.variant %s AND
            Language.code = %s
            """ % (self.id,
                   variantspec,
                   quote(language_code)),
            clauseTables=['Language'])
        if pofile is None:
            raise KeyError(language_code)
        return pofile

    def queryPOFileByLang(self, language_code, variant=None):
        try:
            pofile = self.getPOFileByLang(language_code, variant)
            return pofile
        except KeyError:
            return None

    def messageCount(self):
        return self.messagecount

    def currentCount(self, language):
        try:
            return self.getPOFileByLang(language).currentCount()
        except KeyError:
            return 0

    def updatesCount(self, language):
        try:
            return self.getPOFileByLang(language).updatesCount()
        except KeyError:
            return 0

    def rosettaCount(self, language):
        try:
            return self.getPOFileByLang(language).rosettaCount()
        except KeyError:
            return 0

    def hasMessageID(self, messageID):
        results = POTMsgSet.selectBy(
            potemplateID=self.id, primemsgid_ID=messageID.id)
        return results.count() > 0

    def hasPluralMessage(self):
        results = POMsgIDSighting.select('''
            pluralform = 1 AND
            potmsgset IN (SELECT id FROM POTMsgSet WHERE potemplate = %d)
            ''' % self.id)
        return results.count() > 0

    # Methods defined in IEditPOTemplate
    def expireAllMessages(self):
        """See IPOTemplate."""
        for potmsgset in self:
            potmsgset.sequence = 0

    def getOrCreatePOFile(self, language_code, variant=None, owner=None):
        """See IPOFile."""
        # see if one exists already
        existingpo = self.queryPOFileByLang(language_code, variant)
        if existingpo is not None:
            return existingpo

        # since we don't have one, create one
        try:
            language = Language.byCode(language_code)
        except SQLObjectNotFound:
            raise LanguageNotFound(language_code)

        now = datetime.datetime.now()
        data = {
            'year': now.year,
            'languagename': language.englishname,
            'languagecode': language_code,
            'date': now.isoformat(' '),
            'templatedate': self.datecreated,
            'copyright': '(c) %d Canonical Ltd, and Rosetta Contributors'
                         % now.year,
            'nplurals': language.pluralforms or 1,
            'pluralexpr': language.pluralexpression or '0',
            }

        if self.productrelease is not None:
            data['origin'] = self.productrelease.product.name
        else:
            data['origin'] = self.sourcepackagename.name

        if owner is None:
            # All POFiles should have an owner, by default, the Ubuntu
            # Translators team.
            # XXX: Carlos Perello Marin 2005-04-15: We should get a better
            # default depending on the POFile and the associated POTemplate.
            # The import is here to prevent circular dependencies
            from canonical.launchpad.database.person import PersonSet

            # XXX Carlos Perello Marin 2005-03-28
            # This should be done with a celebrity.
            personset = PersonSet()
            owner = personset.getByName('ubuntu-translators')

        return POFile(potemplate=self,
                      language=language,
                      topcomment=standardPOFileTopComment % data,
                      header=standardPOFileHeader % data,
                      fuzzyheader=True,
                      owner=owner,
                      pluralforms=data['nplurals'],
                      variant=variant)

    def createMessageIDSighting(self, potmsgset, messageID):
        """Creates in the database a new message ID sighting.

        Returns None.
        """
        POMsgIDSighting(
            potmsgsetID=potmsgset.id,
            pomsgid_ID=messageID.id,
            datefirstseen=UTC_NOW,
            datelastseen=UTC_NOW,
            inlastrevision=True,
            pluralform=0)

    def createMessageSetFromMessageID(self, messageID):
        """Creates in the database a new message set.

        As a side-effect, creates a message ID sighting in the database for the
        new set's prime message ID.

        Returns that message set.
        """
        messageSet = POTMsgSet(
            primemsgid_=messageID,
            sequence=0,
            potemplate=self,
            commenttext=None,
            filereferences=None,
            sourcecomment=None,
            flagscomment=None)
        self.createMessageIDSighting(messageSet, messageID)
        return messageSet

    def createMessageSetFromText(self, text):
        # This method used to accept 'text' parameters being string objects,
        # but this is depracated.
        if not isinstance(text, unicode):
            raise TypeError("Message ID text must be unicode: %r", text)

        try:
            messageID = POMsgID.byMsgid(text)
            if self.hasMessageID(messageID):
                raise KeyError(
                    "There is already a message set for this template, file "
                    "and primary msgid")
        except SQLObjectNotFound:
            # If there are no existing message ids, create a new one.
            # We do not need to check whether there is already a message set
            # with the given text in this template.
            messageID = POMsgID(msgid=text)

        return self.createMessageSetFromMessageID(messageID)

    def invalidateCache(self):
        """See IPOTemplate."""
        for pofile in self.pofiles:
            pofile.invalidateCache()

    # ICanAttachRawFileData implementation

    def attachRawFileData(self, contents, published, importer=None):
        """See ICanAttachRawFileData."""

        # a POTemplate is ALWAYS "published"
        assert published == True, 'POTemplate is always "published"'

        filename = '%s.pot' % self.potemplatename.translationdomain
        helpers.attachRawFileData(self, filename, contents, importer)

    # IRawFileData implementation

    # Any use of this interface should adapt this object as an IRawFileData.

    rawfile = ForeignKey(foreignKey='LibraryFileAlias', dbName='rawfile',
                         notNull=True)
    rawimporter = ForeignKey(foreignKey='Person', dbName='rawimporter',
        notNull=True)
    daterawimport = UtcDateTimeCol(dbName='daterawimport', notNull=True,
        default=UTC_NOW)
    rawimportstatus = EnumCol(dbName='rawimportstatus', notNull=True,
        schema=RosettaImportStatus, default=RosettaImportStatus.IGNORE)

    # preserve the interface semantics
    @property
    def rawfilepublished(self):
        return True

    def doRawImport(self, logger=None):
        """See IRawFileData."""
        rawdata = helpers.getRawFileData(self)

        file = StringIO.StringIO(rawdata)

        try:
            import_po(self, file)
        except (POSyntaxError, POInvalidInputError):
            # The import failed, we mark it as failed so we could review it
            # later in case it's a bug in our code.
            self.rawimportstatus = RosettaImportStatus.FAILED
            if logger:
                logger.warning(
                    'We got an error importing %s', self.title, exc_info=1)
            return

        # The import has been done, we mark it that way.
        self.rawimportstatus = RosettaImportStatus.IMPORTED

        # Ask for a sqlobject sync before reusing the data we just
        # updated.
        flush_database_updates()

        # We update the cached value that tells us the number of msgsets
        # this .pot file has
        self.messagecount = self.getPOTMsgSetsCount()

        # And now, we should update the statistics for all po files this
        # .pot file has because msgsets will have changed.
        for pofile in self.pofiles:
            pofile.updateStatistics()


class POTemplateSubset:
    implements(IPOTemplateSubset)

    def __init__(self, sourcepackagename=None,
                 distrorelease=None, productrelease=None):
        """Create a new POTemplateSubset object.

        The set of POTemplate depends on the arguments you pass to this
        constructor. The sourcepackagename, distrorelease and productrelease
        are just filters for that set.
        """
        self.sourcepackagename = sourcepackagename
        self.distrorelease = distrorelease
        self.productrelease = productrelease

        if (productrelease is not None and (distrorelease is not None or
            sourcepackagename is not None)):
            raise ValueError(
                'A product release must not be used with a source package name'
                ' or a distro release.')
        elif productrelease is not None:
            self.query = ('POTemplate.productrelease = %d' % productrelease.id)
            self.orderby = None
            self.clausetables = None
        elif distrorelease is not None and sourcepackagename is not None:
            self.query = ('POTemplate.sourcepackagename = %d AND'
                          ' POTemplate.distrorelease = %d ' %
                          (sourcepackagename.id, distrorelease.id))
            self.orderby = None
            self.clausetables = None
        elif distrorelease is not None:
            self.query = (
                'POTemplate.distrorelease = DistroRelease.id AND'
                ' DistroRelease.id = %d' % distrorelease.id)
            self.orderby = 'DistroRelease.name'
            self.clausetables = ['DistroRelease']
        else:
            raise ValueError(
                'You need to specify the kind of subset you want.')

    def __iter__(self):
        """See IPOTemplateSubset."""
        res = POTemplate.select(self.query, clauseTables=self.clausetables,
                                orderBy=self.orderby)

        for potemplate in res:
            yield potemplate

    def __getitem__(self, name):
        """See IPOTemplateSubset."""
        try:
            ptn = POTemplateName.byName(name)
        except SQLObjectNotFound:
            raise NotFoundError, name

        if self.query is None:
            query = 'POTemplate.potemplatename = %d' % ptn.id
        else:
            query = '%s AND POTemplate.potemplatename = %d' % (
                    self.query, ptn.id)

        result = POTemplate.selectOne(query, clauseTables=self.clausetables)
        if result is None:
            raise NotFoundError, name
        return result

    @property
    def title(self):
        titlestr = ''
        if self.distrorelease:
            titlestr += ' ' + self.distrorelease.displayname
        if self.sourcepackagename:
            titlestr += ' ' + self.sourcepackagename.name
        if self.productrelease:
            titlestr += ' '
            titlestr += self.productrelease.productseries.product.displayname
            titlestr += ' ' + self.productrelease.version
        return titlestr

    def new(self, potemplatename, contents, owner):
        if self.sourcepackagename is not None:
            sourcepackagename_id = self.sourcepackagename.id
        else:
            sourcepackagename_id = None
        if self.distrorelease is not None:
            distrorelease_id = self.distrorelease.id
        else:
            distrorelease_id = None
        if self.productrelease is not None:
            productrelease_id = self.productrelease.id
        else:
            productrelease_id = None

        filename = '%s.pot' % potemplatename.translationdomain
        alias = helpers.uploadRosettaFile(filename, contents)
        return POTemplate(potemplatenameID=potemplatename.id,
                          sourcepackagenameID=sourcepackagename_id,
                          distroreleaseID=distrorelease_id,
                          productreleaseID=productrelease_id,
                          ownerID=owner.id,
                          daterawimport=UTC_NOW,
                          rawfile=alias,
                          rawimporterID=owner.id,
                          rawimportstatus=RosettaImportStatus.PENDING)


class POTemplateSet:
    implements(IPOTemplateSet)

    def __iter__(self):
        """See IPOTemplateSet."""
        res = POTemplate.select()
        for potemplate in res:
            yield potemplate

    def __getitem__(self, name):
        """See IPOTemplateSet."""
        try:
            ptn = POTemplateName.byName(name)
        except SQLObjectNotFound:
            raise NotFoundError, name

        result = POTemplate.selectOne('POTemplate.potemplatename = %d' % ptn.id)
        if result is None:
            raise NotFoundError, name
        return result

    def getSubset(self, **kw):
        """See IPOTemplateSet."""
        if kw.get('distrorelease'):
            # XXX: Should this really be an assert?
            #      -- SteveAlexander 2005-04-23
            assert 'productrelease' not in kw

            distrorelease = kw['distrorelease']

            if kw.get('sourcepackagename'):
                sourcepackagename = kw['sourcepackagename']
                return POTemplateSubset(
                    distrorelease=distrorelease,
                    sourcepackagename=sourcepackagename)
            else:
                return POTemplateSubset(distrorelease=distrorelease)

        # XXX: Should this really be an assert?
        #      -- SteveAlexander 2005-04-23
        assert kw.get('productrelease')
        return POTemplateSubset(productrelease=kw['productrelease'])

    def getTemplatesPendingImport(self):
        """See IPOTemplateSet."""
        results = POTemplate.selectBy(
            rawimportstatus=RosettaImportStatus.PENDING)

        # XXX: Carlos Perello Marin 2005-03-24
        # Really ugly hack needed to do the initial import of the whole hoary
        # archive. It will disappear as soon as the whole
        # LaunchpadPackagePoAttach and LaunchpadPoImport are implemented so
        # rawfile is not used anymore and we start using Librarian.
        # The problem comes with the memory requirements to get more than 7500
        # rows into memory with about 200KB - 300KB of data each one.
        total = results.count()
        done = 0
        while done < total:
            for potemplate in results[done:done+100]:
                yield potemplate
            done = done + 100


class LanguageNotFound(ValueError):
    """Raised when a a language does not exists in the database."""


