# Copyright 2004-2005 Canonical Ltd.  All rights reserved.

__metaclass__ = type

"""Package information classes.

This classes are responsable for fetch and hold the information inside
the sources and binarypackages.
"""

__all__ = ['AbstractPackageData', 'SourcePackageData', 'BinaryPackageData']

import re
import os
import tempfile
import shutil
import rfc822

from canonical import encoding

from canonical.archivepublisher import Poolifier
from canonical.launchpad.scripts.gina.changelog import parse_changelog

from canonical.database.constants import nowUTC
from canonical.lp.dbschema import (GPGKeyAlgorithm,
    PackagePublishingPriority, SourcePackageUrgency)

from canonical.launchpad.scripts import log
from canonical.launchpad.scripts.gina import call

from canonical.launchpad.validators.version import valid_debian_version

# Stash a reference to the poolifier method
poolify = Poolifier().poolify

#
# Data setup
#

urgencymap = {
    "low": SourcePackageUrgency.LOW,
    "medium": SourcePackageUrgency.MEDIUM,
    "high": SourcePackageUrgency.HIGH,
    "emergency": SourcePackageUrgency.EMERGENCY,
    }   

prioritymap = {
    "required": PackagePublishingPriority.REQUIRED,
    "important": PackagePublishingPriority.IMPORTANT,
    "standard": PackagePublishingPriority.STANDARD,
    "optional": PackagePublishingPriority.OPTIONAL,
    "extra": PackagePublishingPriority.EXTRA,
    # Some binarypackages ended up with priority source, apparently
    # because of a bug in dak.
    "source": PackagePublishingPriority.EXTRA,
}

GPGALGOS = {}
for item in GPGKeyAlgorithm.items:
    GPGALGOS[item.value] = item.name

#
# Helper functions
#

def stripseq(seq):
    return [s.strip() for s in seq]


def get_dsc_path(name, version, directory):
    # Note that this is also used in handlers.py
    version = re.sub("^\d+:", "", version)
    filename = "%s_%s.dsc" % (name, version)
    fullpath = os.path.join(directory, filename)
    if not os.path.exists(fullpath):
        # If we didn't find this file in the archive, things are
        # pretty bad, so stop processing immediately
        raise PoolFileNotFound("File %s not in archive (%s)" % 
                               (filename, fullpath))
    return filename, fullpath


def read_dsc(package, version, directory, package_root):
    urgency = None

    dsc_name, dsc_path = get_dsc_path(package, version,
        os.path.join(package_root, directory))
    dsc = open(dsc_path).read().strip()

    call("dpkg-source -sn -x %s" % dsc_path)

    version = re.sub("^\d+:", "", version)
    version = re.sub("-[^-]+$", "", version)
    filename = "%s-%s" % (package, version)
    fullpath = os.path.join(filename, "debian", "changelog")

    if os.path.exists(fullpath):
        clfile = open(fullpath)
        line = ""
        while not line:
            line = clfile.readline().strip()
        if "urgency=" in line:
            urgency = line.split("urgency=")[1].strip().lower()
        clfile.seek(0)
        changelog = parse_changelog(clfile)
        clfile.close()
    else:
        log.warn("No changelog file found for %s in %s" % (package, filename))
        changelog = None

    # Look for the license. License is an interesting case: we obtain it
    # when opening the DSC file, but we only really do this when
    # creating a BinaryPackageRelease, because that's where it needs to
    # be stored.
    fullpath = os.path.join(filename, "debian", "copyright")
    if os.path.exists(fullpath):
        licence = open(fullpath).read().strip()
    else:
        log.warn("No license file found for %s in %s" % (package, filename))
        licence = None
    return dsc, urgency, changelog, licence


def parse_person(val):
    if "," in val:
        # Some emails have ',' like "Adam C. Powell, IV
        # <hazelsct@debian.org>". rfc822.parseaddr seems to do not
        # handle this properly, so we munge them here
        val = val.replace(',','')
    return rfc822.parseaddr(val)


def get_person_by_key(keyrings, key):
    # XXX: untested, should probably be a method
    if key and key not in ("NOSIG", "None", "none"):
        command = ("gpg --no-options --no-default-keyring "
                   "--with-colons --fingerprint %s %s" % (key, keyrings))
        h = os.popen(command, "r")
        for line in h.readlines():
            if line.startswith("pub"):
                break
        else:
            log.warn("Broke parsing gpg output for %s" % key)
            return None

        line = line.split(":")
        algo = int(line[3])
        if GPGALGOS.has_key(algo):
            algochar = GPGALGOS[algo]
        else:
            algochar = "?" % algo
        # STRIPPED GPGID Support by cprov 20041004
        #          id = line[2] + algochar + "/" + line[4][-8:]
        id = line[4][-8:]
        algorithm = algo
        keysize = line[2]
        user, rest = line[9].split("<", 1)
        email = rest.split(">")[0].lower()
        if line[1] == "-":
            is_revoked = 0
        else:
            is_revoked = 1

        h = os.popen("gpg --export --no-default-keyring %s "
                     "--armor %s" % (keyrings, key), "r")
        armor = h.read().strip()

        return (user, email, id, armor, is_revoked, algorithm, keysize)
    else:
        return None

#
# Exception classes
#

class MissingRequiredArguments(Exception):
    """Missing Required Arguments Exception.

    Raised if we attempted to construct a SourcePackageData based on an
    invalid Sources.gz entry -- IOW, without all the required arguments.
    This is because we are stuck (for now) passing arguments using
    **args as some of the argument names are not valid Python identifiers
    """


class PackageFileProcessError(Exception):
    """An error occurred while processing a package file"""


class PoolFileNotFound(PackageFileProcessError):
    """The specified file was not found in the archive pool"""


class InvalidVersionError(Exception):
    """An invalid package version was found"""


class InvalidSourceVersionError(Exception):
    """
    An invalid source package version was found when processing a binary
    package.
    """

#
# Implementation classes
#

class AbstractPackageData:
    # This class represents information on a single package that was
    # obtained through the archive. This information comes from either a
    # Sources or Packages file, and is complemented by data scrubbed
    # from the corresponding pool files (the dsc, deb and tar.gz)
    package_root = None
    package = None
    _required = None
    version = None

    def __init__(self):
        if self.version is None or not valid_debian_version(self.version):
            # XXX: untested
            raise InvalidVersionError("%s has an invalid version: %s" %
                                      (self.package, self.version))


        missing = [attr for attr in self._required if not getattr(self, attr)]
        if missing:
            raise MissingRequiredArguments(missing)

    def process_package(self, kdb, package_root, keyrings):
        """Process the package using the files located in the archive.

        Raises PoolFileNotFound if a file is not found in the pool.
        Raises PackageFileProcessError if processing the package itself
        caused an exception.
        """
        self.package_root = package_root

        tempdir = tempfile.mkdtemp()
        cwd = os.getcwd()
        os.chdir(tempdir)
        try:
            try:
                self.do_package(package_root)
            finally:
                os.chdir(cwd)
        except PoolFileNotFound:
            raise
        except Exception, e:
            raise PackageFileProcessError("Failed processing %s (perhaps "
                                          "see %s): %s" %
                                          (self.package, tempdir, e))
        shutil.rmtree(tempdir)

        # XXX: Katie is disabled for the moment; hardcode the
        # date_uploaded and c'est la vie
        #   -- kiko, 2005-10-18
        # if not self.do_katie(kdb, keyrings):
        #    return False
        self.date_uploaded = nowUTC
        self.is_processed = True
        return True

    def do_package(self, package_root):
        raise NotImplementedError

    def do_katie(self, kdb, keyrings):
        raise NotImplementedError

    def ensure_complete(self, kdb):
        raise NotImplementedError


class SourcePackageData(AbstractPackageData):
    """This Class holds important data to a given sourcepackagerelease."""

    # Defaults, overwritten by __init__
    directory = None

    # Defaults, potentially overwritten by __init__
    build_depends = ""
    build_depends_indep = ""
    standards_version = ""

    # Defaults, overwritten by do_package and ensure_required
    section = None

    is_processed = False
    is_created = False

    # These arguments /must/ have been set in the Sources file and
    # supplied to __init__ as keyword arguments. If any are not, a
    # MissingRequiredArguments exception is raised.
    _required = [
        'package', 'binaries', 'version', 'maintainer',
        'architecture', 'directory', 'files', 'format']

    def __init__(self, **args):
        for k, v in args.items():
            if k == 'Binary':
                self.binaries = stripseq(v.split(","))
            elif k == 'Section':
                if "/" in v:
                    self.component, self.section = v.split("/")
                else:
                    self.component, self.section  = "main", v
            elif k == 'Maintainer':
                self.maintainer = parse_person(v)
            elif k == 'Files':
                self.files = []
                files = v.split("\n")
                for f in files:
                    self.files.append(stripseq(f.split(" ")))
            elif k == 'Uploaders':
                # XXX: we don't do anything with this data, but I
                # suspect we should. -- kiko, 2005-10-19
                people = stripseq(v.split(","))
                self.uploaders = [person.split(" ", 1) for person in people]
            else:
                setattr(self, k.lower().replace("-", "_"), v)

        AbstractPackageData.__init__(self)

    def do_package(self, package_root):
        """Get the Changelog and licence from the package on archive.

        If successful processing of the package occurs, this method
        sets the changelog, urgency and licence attributes.
        """
        ret = read_dsc(self.package, self.version, self.directory, 
                       package_root)

        # We don't use the licence here at all
        dsc, urgency, changelog, dummy = ret

        self.dsc = encoding.guess(dsc)
        self.urgency = urgency
        if changelog is None:
            self.changelog = None
        else:
            self.changelog = encoding.guess(changelog[0]["changes"])

    def do_katie(self, kdb, keyrings):
        # XXX: disabled for the moment, untested
        raise AssertionError

        data = kdb.getSourcePackageRelease(self.package, self.version)
        if not data:
            return

        assert len(data) == 1
        data = data[0]
        # self.date_uploaded = data["install_date"]
        #
        #    self.dsc_signing_key = data["fingerprint"]
        #    self.dsc_signing_key_owner = \
        #        get_person_by_key(keyrings, self.dsc_signing_key)

    def ensure_complete(self, kdb):
        if self.section is None:
            # This assumption is a bit evil. There is a hidden issue
            # that manifests itself if the source package was unchanged
            # between releases and its Sources file lacked a section
            # initially and later the section is added: we will never
            # update the record. I doubt this will be an issue in
            # practice.
            if kdb:
                # XXX: untested
                log.warn("Source package %s lacks section, looking it up..." %
                         self.package)
                self.section = kdb.getSourceSection(self.package)
                if '/' in self.section:
                    self.component, self.section = self.section.split("/")
            else:
                self.section = 'misc'
                log.warn("Source package %s lacks section, assumed %r" %
                         (self.package, self.section))

        if self.urgency not in urgencymap:
            log.warn("Invalid urgency in %s, %r, assumed %r" % 
                     (self.package, self.urgency, "low"))
            self.urgency = "low"

        if '/' in self.section:
            # this apparently happens with packages in universe.
            # 3dchess, for instance, uses "universe/games"
            self.section = self.section.split("/", 1)[1]


class BinaryPackageData(AbstractPackageData):
    """This Class holds important data to a given binarypackage."""

    # These attributes must have been set by the end of the __init__ method.
    # They are passed in as keyword arguments. If any are not set, a
    # MissingRequiredArguments exception is raised.
    _required = [
        'package', 'installed_size', 'maintainer',
        'architecture', 'version', 'filename',
        'size', 'md5sum', 'description', 'summary']

    # Set in __init__
    source = None
    source_version = None
    version = None
    architecture = None
    filename = None

    # Defaults, optionally overwritten in __init__
    depends = ""
    suggests = ""
    recommends = ""
    conflicts = ""
    replaces = ""
    provides = ""
    essential = False

    # Overwritten in do_package, optionally
    shlibs = ""

    # Overwritten by __init__ and ensure_required
    section = None
    priority = None

    #
    is_processed = False
    is_created = False
    #
    source_version_re = re.compile(r'([^ ]+) +\(([^\)]+)\)')
    def __init__(self, **args):
        for k, v in args.items():
            if k == "Maintainer":
                self.maintainer = parse_person(v)
            elif k == "Essential":
                self.essential = (v == "yes")
            elif k == "Description":
                self.description = encoding.guess(v)
                summary = self.description.split("\n")[0].strip()
                if not summary.endswith('.'):
                    summary = summary + '.'
                self.summary = summary
            elif k == "Installed-Size":
                try:
                    self.installed_size = int(v)
                except ValueError:
                    raise MissingRequiredArguments("Installed-Size is "
                        "not a valid integer: %r" % v)
            else:
                setattr(self, k.lower().replace("-", "_"), v)
            # XXX: "enhances" is not used and not stored anywhere
            # XXX: same for "pre_depends"

        if self.source:
            # We need to handle cases like "Source: myspell
            # (1:3.0+pre3.1-6)". apt-pkg kindly splits this for us
            # already, but sometimes fails.
            # XXX: dsilvers: 20050922: Work out why this happens and
            # file an upstream bug against python-apt once we've worked
            # it out.
            if self.source_version is None:
                match = self.source_version_re.match(self.source)
                if match:
                    self.source = match.group(1)
                    self.source_version = match.group(2)
                else:
                    # XXX: this is probably a best-guess and might fail
                    #   -- kiko, 2005-10-18
                    self.source_version = self.version
        else:
            # Some packages have Source, some don't -- the ones that
            # don't have the same package name.
            self.source = self.package
            self.source_version = self.version

        if (self.source_version is None or
            not valid_debian_version(self.source_version)):
            raise InvalidSourceVersionError("Binary package %s (%s) "
                "refers to source package %s with invalid version: %s" %
                (self.package, self.version, self.source, self.source_version))

        AbstractPackageData.__init__(self)

    def do_package(self, package_root):
        """Grab shared library info from package in archive if it exists."""
        fullpath = os.path.join(package_root, self.filename)
        if not os.path.exists(fullpath):
            raise PoolFileNotFound('%s not found' % fullpath)

        call("dpkg -e %s" % fullpath)
        shlibfile = os.path.join("DEBIAN", "shlibs")
        if os.path.exists(shlibfile):
            # XXX: untested
            log.debug("Grabbing shared library info from %s" % 
                      os.path.basename(fullpath))
            self.shlibs = open(shlibfile).read().strip()

        # XXX: using self.component here is wrong. What we need here is
        # a locate_source_package_in_pool() function that finds it and
        # returns it.
        directory = os.path.join("pool",
            poolify(self.source, self.component))

        # XXX: we could probably refactor read_dsc into three parts, one
        # that unpacked the file and two consumers that read specific
        # data from it.
        ret = read_dsc(self.source, self.source_version,
                       directory, package_root)
        dummy, dummy, dummy, licence = ret
        self.licence = encoding.guess(licence)

    def do_katie(self, kdb, keyrings):
        # XXX: disabled for the moment, untested
        raise AssertionError

        data = kdb.getBinaryPackageRelease(self.package, self.version,
                                           self.architecture)
        if not data:
            return

        assert len(data) >= 1
        data = data[0]

        self.gpg_signing_key = data["fingerprint"]
        log.debug(self.gpg_signing_key)
        self.gpg_signing_key_owner = \
            get_person_by_key(keyrings, self.gpg_signing_key)
        return True

    def ensure_complete(self, kdb):
        if self.section is None:
            self.section = 'misc'
            log.warn("Binary package %s lacks a section... assumed %r" %
                     (self.package, self.section))

        if self.priority is None:
            self.priority = 'extra'
            log.warn("Binary package %s lacks valid priority, assumed %r" %
                     (self.package, self.section))

