# Copyright 2004-2009 Canonical Ltd.  All rights reserved.
# pylint: disable-msg=W0401,C0301

__metaclass__ = type

# XXX flacoste 2009/03/18 We should use specific imports instead of
# importing from this module.

from canonical.launchpad.interfaces.launchpad import *
from canonical.launchpad.interfaces.malone import *
from canonical.launchpad.interfaces.validation import *

# these need to be at the top, because the others depend on them sometimes
from lp.blueprints.interfaces.specificationtarget import *
from lp.registry.interfaces.person import *
from lp.registry.interfaces.pillar import *

from canonical.launchpad.interfaces.account import *
from lp.soyuz.interfaces.archivedependency import *
from lp.soyuz.interfaces.archivepermission import *
from lp.soyuz.interfaces.archivesubscriber import *
from lp.registry.interfaces.announcement import *
from canonical.launchpad.interfaces.authserver import *
from canonical.launchpad.interfaces.authtoken import *
from lp.soyuz.interfaces.binarypackagerelease import *
from lp.soyuz.interfaces.binarypackagename import *
from canonical.launchpad.interfaces.bounty import *
from canonical.launchpad.interfaces.bountymessage import *
from canonical.launchpad.interfaces.bountysubscription import *
from lp.code.interfaces.branch import *
from lp.code.interfaces.branchmergeproposal import *
from lp.code.interfaces.branchref import *
from lp.code.interfaces.branchrevision import *
from lp.code.interfaces.branchsubscription import *
from lp.code.interfaces.branchvisibilitypolicy import *
from canonical.launchpad.interfaces.bugactivity import *
from canonical.launchpad.interfaces.bugattachment import *
from canonical.launchpad.interfaces.bug import *
from canonical.launchpad.interfaces.bugbranch import *
from canonical.launchpad.interfaces.bugcve import *
from canonical.launchpad.interfaces.buglink import *
from canonical.launchpad.interfaces.bugmessage import *
from canonical.launchpad.interfaces.bugnomination import *
from canonical.launchpad.interfaces.bugnotification import *
from canonical.launchpad.interfaces.bugsubscription import *
from canonical.launchpad.interfaces.bugsupervisor import *
from canonical.launchpad.interfaces.bugtask import *
from canonical.launchpad.interfaces.bugtarget import *
from canonical.launchpad.interfaces.bugtracker import *
from canonical.launchpad.interfaces.bugwatch import *
from lp.soyuz.interfaces.build import *
from lp.soyuz.interfaces.builder import *
from lp.soyuz.interfaces.buildrecords import *
from lp.soyuz.interfaces.buildqueue import *
from lp.code.interfaces.codeimport import *
from lp.code.interfaces.codeimportevent import *
from lp.code.interfaces.codeimportjob import *
from lp.code.interfaces.codeimportmachine import *
from lp.code.interfaces.codeimportscheduler import *
from lp.registry.interfaces.codeofconduct import *
from lp.code.interfaces.codereviewcomment import *
from lp.code.interfaces.codereviewvote import *
from lp.registry.interfaces.commercialsubscription import *
from lp.soyuz.interfaces.component import *
from canonical.launchpad.interfaces.country import *
from canonical.launchpad.interfaces.customlanguagecode import *
from canonical.launchpad.interfaces.cve import *
from canonical.launchpad.interfaces.cvereference import *
from lp.registry.interfaces.distribution import *
from canonical.launchpad.interfaces.distributionbounty import *
from lp.registry.interfaces.distributionmirror import *
from lp.registry.interfaces.distributionsourcepackage import *
from lp.soyuz.interfaces.distributionsourcepackagecache import *
from lp.soyuz.interfaces.distributionsourcepackagerelease import *
from lp.soyuz.interfaces.distroarchseries import *
from lp.soyuz.interfaces.distroarchseriesbinarypackage import *
from lp.soyuz.interfaces.distroarchseriesbinarypackagerelease\
    import *
from lp.registry.interfaces.distroseries import *
from lp.soyuz.interfaces.distroseriesbinarypackage import *
from canonical.launchpad.interfaces.distroserieslanguage import *
from lp.soyuz.interfaces.distroseriespackagecache import *
from lp.soyuz.interfaces.distroseriessourcepackagerelease import *
from canonical.launchpad.interfaces.emailaddress import *
from lp.registry.interfaces.entitlement import *
from canonical.launchpad.interfaces.externalbugtracker import *
from lp.registry.interfaces.featuredproject import *
from lp.soyuz.interfaces.files import *
from canonical.launchpad.interfaces.geoip import *
from lp.registry.interfaces.gpg import *
from canonical.launchpad.interfaces.gpghandler import *
from canonical.launchpad.interfaces.hwdb import *
from lp.registry.interfaces.irc import *
from lp.registry.interfaces.jabber import *
from lp.registry.interfaces.karma import *
from canonical.launchpad.interfaces.language import *
from canonical.launchpad.interfaces.languagepack import *
from canonical.launchpad.interfaces.launchpad import *
from canonical.launchpad.interfaces.launchpadstatistic import *
from canonical.launchpad.interfaces.librarian import *
from lp.registry.interfaces.location import *
from canonical.launchpad.interfaces.logintoken import *
from canonical.launchpad.interfaces.lpstorm import *
from canonical.launchpad.interfaces.mail import *
from canonical.launchpad.interfaces.mailbox import *
from lp.registry.interfaces.mailinglist import *
from lp.registry.interfaces.mailinglistsubscription import *
from lp.registry.interfaces.mentoringoffer import *
from canonical.launchpad.interfaces.message import *
from lp.registry.interfaces.milestone import *
from canonical.launchpad.interfaces.oauth import *
from canonical.launchpad.interfaces.openidconsumer import *
from lp.soyuz.interfaces.package import *
from canonical.launchpad.interfaces.packagerelationship import *
from canonical.launchpad.interfaces.packaging import *
from canonical.launchpad.interfaces.pathlookup import *
from canonical.launchpad.interfaces.pofile import *
from canonical.launchpad.interfaces.pofiletranslator import *
from lp.registry.interfaces.poll import *
from canonical.launchpad.interfaces.pomsgid import *
from canonical.launchpad.interfaces.potemplate import *
from canonical.launchpad.interfaces.potmsgset import *
from canonical.launchpad.interfaces.potranslation import *
from lp.soyuz.interfaces.processor import *
from lp.registry.interfaces.product import *
from canonical.launchpad.interfaces.productbounty import *
from lp.registry.interfaces.productlicense import *
from lp.registry.interfaces.productrelease import *
from lp.registry.interfaces.productseries import *
from lp.registry.interfaces.project import *
from canonical.launchpad.interfaces.projectbounty import *
from lp.soyuz.interfaces.publishedpackage import *
from lp.soyuz.interfaces.publishing import *
from lp.soyuz.interfaces.queue import *
from lp.code.interfaces.revision import *
from canonical.launchpad.interfaces.rosettastats import *
from lp.registry.interfaces.salesforce import *
from canonical.launchpad.interfaces.schema import *
from canonical.launchpad.interfaces.scriptactivity import *
from lp.soyuz.interfaces.section import *
from canonical.launchpad.interfaces.searchservice import *
from lp.registry.interfaces.sourcepackage import *
from lp.registry.interfaces.sourcepackagename import *
from lp.soyuz.interfaces.sourcepackagerelease import *
from lp.blueprints.interfaces.specification import *
from lp.blueprints.interfaces.specificationbranch import *
from lp.blueprints.interfaces.specificationbug import *
from lp.blueprints.interfaces.specificationdependency import *
from lp.blueprints.interfaces.specificationfeedback import *
from lp.blueprints.interfaces.specificationsubscription import *
from canonical.launchpad.interfaces.spokenin import *
from lp.blueprints.interfaces.sprint import *
from lp.blueprints.interfaces.sprintattendance import *
from lp.blueprints.interfaces.sprintspecification import *
from lp.registry.interfaces.ssh import *
from canonical.launchpad.interfaces.structuralsubscription import *
from lp.registry.interfaces.teammembership import *
from canonical.launchpad.interfaces.temporaryblobstorage import *
from canonical.launchpad.interfaces.translationcommonformat import *
from canonical.launchpad.interfaces.translationexporter import *
from canonical.launchpad.interfaces.translationfileformat import *
from canonical.launchpad.interfaces.translationimporter import *
from canonical.launchpad.interfaces.translationmessage import *
from canonical.launchpad.interfaces.translations import *
from canonical.launchpad.interfaces.translationsoverview import *
from canonical.launchpad.interfaces.translationsperson import *
from canonical.launchpad.interfaces.translationtemplateitem import *
from canonical.launchpad.interfaces.translationcommonformat import *
from canonical.launchpad.interfaces.translationgroup import *
from canonical.launchpad.interfaces.translationimportqueue import *
from canonical.launchpad.interfaces.translator import *
from canonical.launchpad.interfaces.vpoexport import *
from canonical.launchpad.interfaces.vpotexport import *
from lp.registry.interfaces.wikiname import *
from canonical.launchpad.interfaces.poexportrequest import *
from lp.soyuz.interfaces.packagediff import *
from lp.soyuz.interfaces.packageset import *

from lp.answers.interfaces.answercontact import *
from lp.answers.interfaces.faq import *
from lp.answers.interfaces.faqcollection import *
from lp.answers.interfaces.faqtarget import *
from lp.answers.interfaces.question import *
from lp.coop.answersbugs.interfaces import *
from lp.answers.interfaces.questioncollection import *
from lp.answers.interfaces.questionenums import *
from lp.answers.interfaces.questionmessage import *
from lp.answers.interfaces.questionreopening import *
from lp.answers.interfaces.questionsubscription import *
from lp.answers.interfaces.questiontarget import *

from canonical.launchpad.interfaces._schema_circular_imports import *

