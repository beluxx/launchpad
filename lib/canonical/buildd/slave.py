# Copyright Canonical Limited
# Author: Daniel Silverstone <daniel.silverstone@canonical.com>

# Buildd Slave implementation

import xmlrpclib
from os.path import isdir, exists
from os import mkdir, symlink, kill, environ, remove
from signal import SIGKILL
import sha
from twisted.internet import protocol
from twisted.internet import reactor
from twisted.web import xmlrpc
from canonical.librarian.client import FileDownloadClient

class RunCapture(protocol.ProcessProtocol):
    """Run a command and capture its output to a slave's log"""

    def __init__(self, slave, callback):
        # Erm, did someone change twisted when I wasn't looking?
        # XXX: dsilvers: 20050329: Should I be calling this or something
        # like it?
        #protocol.ProcessProtocol.__init__(self)
        self.slave = slave
        self.notify = callback

    def outReceived(self, data):
        self.slave.log(data)

    def processEnded(self, statusobject):
        self.notify(statusobject.value.exitCode)

class BuildManager(object):
    """Build Daemon slave build manager abstract parent
    """

    def __init__(self, slave, buildid):
        object.__init__(self)
        self._buildid = buildid
        self._slave = slave
        self._unpackpath = slave._config.get("allmanagers", "unpackpath")
        self._cleanpath = slave._config.get("allmanagers", "cleanpath")
        self._mountpath = slave._config.get("allmanagers", "mountpath")
        self._umountpath = slave._config.get("allmanagers", "umountpath")
        
    def runSubProcess(self, command, args):
        """Run a sub process capturing the results in the log."""
        self._subprocess = RunCapture(self._slave, self.iterate)
        self._slave.log("RUN: %s %r\n" % (command,args))
        reactor.spawnProcess(self._subprocess, command, args,
                             env=environ, path=environ["HOME"])

    def _unpackChroot(self, chroottarfile):
        """Unpack the buld chroot."""
        self.runSubProcess(self._unpackpath,
                           [ "unpack-chroot", self._buildid, chroottarfile ])

    def doCleanup(self):
        """Remove the build tree etc."""
        self.runSubProcess( self._cleanpath,
                        ["remove-build", self._buildid] )

    def doMounting(self):
        """Mount things in the chroot, e.g. proc."""
        self.runSubProcess( self._mountpath,
                            ["mount-chroot", self._buildid] )
        
    def doUnmounting(self):
        """Unmount the chroot."""
        self.runSubProcess( self._umountpath,
                            ["umount-chroot", self._buildid] )

    def initiate(self, files, chroot):
        """Initiate a build given the input files"""
        mkdir("%s/build-%s" % (environ["HOME"], self._buildid))
        for f in files:
            symlink( self._slave.cachePath(files[f]), "%s/build-%s/%s" % (environ["HOME"], self._buildid, f) )
        self._unpackChroot(self._slave.cachePath(chroot))

    def iterate(self, success):
        """Perform an iteration of the slave.

        The BuildManager tends to work by invoking several
        subprocesses in order. the iterate method is called by the
        object created by runSubProcess to gather the results of the
        sub process.
        """
        raise NotImplementedError, "BuildManager should be subclassed to be used"

    def abort(self):
        """Abort the build by killing the subprocess."""
        if not self.alreadyfailed:
            self.alreadyfailed = True
        self.subprocess.transport.signalProcess('KILL')

class BuilderStatus:
    """Status values for the builder."""
    
    IDLE = "BuilderStatus.IDLE"
    BUILDING = "BuilderStatus.BUILDING"
    WAITING = "BuilderStatus.WAITING"
    ABORTED = "BuilderStatus.ABORTED"

    UNKNOWNSUM = "BuilderStatus.UNKNOWN-SUM"
    UNKNOWNBUILDER = "BuilderStatus.UNKNOWN-BUILDER"
    

class BuildStatus:
    """Status values for builds themselves."""
    
    OK = "BuildStatus.OK"
    DEPFAIL = "BuildStatus.DEPFAIL"
    PACKAGEFAIL = "BuildStatus.PACKAGEFAIL"
    CHROOTFAIL = "BuildStatus.CHROOTFAIL"
    BUILDERFAIL = "BuildStatus.BUILDERFAIL"
    
class BuildDSlave(object):
    """Build Daemon slave.

    XXX: dsilvers: 20050317: Fill this in
    """

    def __init__(self, config):
        object.__init__(self)
        self._config = config
        self.builderstatus = BuilderStatus.IDLE
        self._cachepath = self._config.get("slave","filecache")
        self.buildstatus = BuildStatus.OK
        self.waitingfiles = {}
        librarian_host = environ.get('LB_HOST', 'localhost')
        librarian_port = int(environ.get('LB_DPORT', '8000'))


        self.downloader = FileDownloadClient(librarian_host, librarian_port)
        
        if not isdir(self._cachepath):
            raise ValueError, "FileCache path is not a dir"
        
    def getArch(self):
        """Return the Architecture tag for the slave."""
        return self._config.get("slave","architecturetag")

    def cachePath(self, file):
        """Return the path in the cache of the file specified."""
        return "%s/%s" % (self._cachepath, file)

    def testPresent(self, sha1sum, alias=None):
        """Check for the file with the checksum specified.

        Optionally you can provide the libraryfilealias and
        the build slave will fetch the file if it doesn't have it.
        """
        if alias is not None:
            if not exists(self.cachePath(sha1sum)):
                print "Fetching %s by alias %s" % (sha1sum,alias)
                f = self.downloader.getFileByAlias(alias)
                of = open(self.cachePath(sha1sum),"w")
                for chunk in iter(lambda: f.read(4096), ''):
                    of.write(chunk)
                of.close()
                f.close()
        return exists(self.cachePath(sha1sum))

    def storeFile(self, content):
        """Take the provided content and store it in the file cache."""
        sha1sum = sha.sha(content).hexdigest()
        if self.testPresent(sha1sum):
            return sha1sum
        f = open(self.cachePath(sha1sum), "w")
        f.write(content)
        f.close()
        return sha1sum

    def fetchFile(self, sha1sum):
        """Fetch the file of the given sha1sum."""
        if not self.testPresent(sha1sum):
            raise ValueError, "Unknown SHA1sum %s" % sha1sum
        f = open(self.cachePath(sha1sum), "r")
        c = f.read()
        f.close()
        return c

    def abort(self):
        """Abort the current build."""
        # XXX: dsilvers: 2005/01/21: Current abort mechanism doesn't wait
        # for abort to complete. This is potentially an issue in a heavy
        # load situation
        if self.builderstatus != BuilderStatus.BUILDING:
            raise ValueError, "Slave is not BUILDING when asked to abort"
        self.manager.abort()
        self.builderstatus = BuilderStatus.ABORTED

    def clean(self):
        """Clean up pending files and reset the internal build state."""
        if self.builderstatus != BuilderStatus.WAITING:
            raise ValueError, "Slave is not WAITING when asked to clean"
        for f in self.waitingfiles:
            remove(self.cachePath(self.waitingfiles[f]))
        self.builderstatus = BuilderStatus.IDLE
        self._log = ""
        self.waitingfiles = {}
        self.manager = None
        self.buildstatus = BuildStatus.OK

    def emptyLog(self):
        """Empty the stored log."""
        self._log = ""

    def log(self, data):
        # XXX: dsilvers: 2005/01/21: Largest build log I've seen is 50 megs
        # but we might have to consider using a disk file if that gets worse
        self._log += data
        if data.endswith("\n"):
            data = data[:-1]
        print "Build log: " + data

    def fetchLogTail(self, amount=None):
        """Get the last 'amount' bytes of the log.
        
        This will only return whole lines, so it may return less than 'amount'
        bytes.
        
        If amount is -1, this will return the entire log.
        """
        if amount is None:
            return self._log
        ret = self._log[-amount:]
        return ret[ret.find("\n")+1:]
    
    def startBuild(self, manager):
        """Start a build with the provided BuildManager instance."""
        if self.builderstatus != BuilderStatus.IDLE:
            raise ValueError, "Slave is not IDLE when asked to start building"
        self.manager = manager
        self.builderstatus = BuilderStatus.BUILDING

    def builderFail(self):
        """Cease building because the builder has a problem."""
        if self.builderstatus != BuilderStatus.BUILDING:
            raise ValueError, "Slave is not BUILDING when set to BUILDERFAIL"
        self.builderstatus = BuilderStatus.WAITING
        self.buildstatus = BuildStatus.BUILDERFAIL

    def buildFail(self):
        """Cease building because the package failed to build."""
        if self.builderstatus != BuilderStatus.BUILDING:
            raise ValueError, "Slave is not BUILDING when set to BUILDFAIL"
        self.builderstatus = BuilderStatus.WAITING
        self.buildstatus = BuildStatus.PACKAGEFAIL

    def depFail(self):
        """Cease building due to a dependency issue."""
        if self.builderstatus != BuilderStatus.BUILDING:
            raise ValueError, "Slave is not BUILDING when set to DEPFAIL"
        self.builderstatus = BuilderStatus.WAITING
        self.buildstatus = BuildStatus.DEPFAIL

    def buildComplete(self):
        """Mark the build as complete and waiting interaction from the build
        daemon master."""
        if self.builderstatus != BuilderStatus.BUILDING:
            raise ValueError, "Slave is not BUILDING when told build is complete"
        self.builderstatus = BuilderStatus.WAITING
        self.buildstatus = BuildStatus.OK
        

class XMLRPCBuildDSlave(xmlrpc.XMLRPC):
    """XMLRPC build daemon slave management interface

    """

    def __init__(self, config):
        xmlrpc.XMLRPC.__init__(self)
        self.protocolversion = 1
        self.slave = BuildDSlave(config)
        self._builders = {}
        
        print "Initialised"

    def registerBuilder(self, builderclass, buildertag):
        self._builders[buildertag] = builderclass

    def xmlrpc_echo(self, *args):
        """Echo the argument back."""
        return args

    def xmlrpc_info(self):
        # Return the protocol version and the methods supported
        return self.protocolversion, [
            "info", "status", "fetchlogtail", "doyouhave",
            "storefile", "fetchfile", "abort", "clean", "startbuild"
            ], self.slave.getArch(), self._builders.keys()

    def xmlrpc_status(self):
        """Return the status of the build daemon.

        Depending on the builder status we return differing amounts of
        data. We do however always return the builder status as the first
        value.
        """
        status = self.slave.builderstatus
        statusname = status.split('.')[-1]
        func = getattr(self, "status_" + statusname, None)
        if func is None:
            raise ValueError, "Unknown status " + status
        return (status,) + func()

    def status_IDLE(self):
        """Handler for xmlrpc_status IDLE.

        Returns () since there's nothing to report
        """
        return ()
    
    def status_BUILDING(self):
        """Handler for xmlrpc_status BUILDING.

        Returns the build id and up to one kilobyte of log tail
        """

        return self.buildid, self.slave.fetchLogTail(1024)

    def status_WAITING(self):
        """Handler for xmlrpc_status WAITING.

        Returns the build id and the set of files waiting to be returned
        unless the builder failed in which case we return the buildstatus
        and the build id but no file set.
        """
        if self.slave.buildstatus in (
            BuildStatus.OK, BuildStatus.PACKAGEFAIL, BuildStatus.DEPFAIL ):
            return (self.slave.buildstatus, self.buildid,
                    self.slave.waitingfiles)
        return self.slave.buildstatus, self.buildid

    def status_ABORTED(self):
        """Handler for xmlrpc_status ABORTED.

        Returns the build id only.
        """
        return self.buildid

    def xmlrpc_fetchlogtail(self, amount):
        """Return the requested amount of log information."""
        return self.slave.fetchLogTail(amount)
    
    def xmlrpc_doyouhave(self, sha1sum, alias=None):
        """Return whether or not the slave has the specified file."""
        return self.slave.testPresent(sha1sum, alias)

    def xmlrpc_storefile(self, content):
        """Store the provided content in the slave's cache."""
        return self.slave.storeFile(str(content))
    
    def xmlrpc_fetchfile(self, sha1sum):
        """Fetch the content of the file specified from the slave's cache."""
        return xmlrpclib.Binary(self.slave.fetchFile(sha1sum))

    def xmlrpc_abort(self):
        """Abort the current build."""
        self.slave.abort()
        return BuilderStatus.ABORTED

    def xmlrpc_clean(self):
        """Clean up the waiting files and reset the slave's internal state."""
        self.slave.clean()
        return BuilderStatus.IDLE

    def xmlrpc_startbuild(self, buildid, filemap, chrootsum, builder):
        if not builder in self._builders:
            return BuilderStatus.UNKNOWNBUILDER
        if not self.slave.testPresent(chrootsum):
            return BuilderStatus.UNKNOWNSUM, chrootsum
        for checksum in filemap.itervalues():
            if not self.slave.testPresent(checksum):
                return BuilderStatus.UNKNOWNSUM, checksum
        if buildid is None or buildid == "" or buildid == 0:
            raise ValueError, buildid
        # builder is available, buildd is non empty,
        # filelist is consistent, chrootsum is available, let's initiate...

        self.buildid = buildid
        
        self.slave.startBuild(self._builders[builder](self.slave, buildid))
        self.slave.manager.initiate(filemap, chrootsum)
        return BuilderStatus.BUILDING
    
