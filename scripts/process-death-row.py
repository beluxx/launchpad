#!/usr/bin/env python
"""Death row kickoff script."""

import _pythonpath

import logging
from optparse import OptionParser

from canonical.lp import initZopeless
from canonical.launchpad.database import Distribution
from canonical.launchpad.scripts import (execute_zcml_for_scripts,
                                         logger, logger_options)
from canonical.archivepublisher import (
    DiskPool, Poolifier, POOL_DEBIAN, Config, DeathRow, LucilleConfigError)

def getDeathRow(distroname, log):
    distro = Distribution.byName(distroname)

    log.debug("Grab Lucille config.")
    try:
        pubconf = Config(distro)
    except LucilleConfigError, info:
        log.error(info)
        raise

    log.debug("Preparing on-disk pool representation.")
    dp = DiskPool(Poolifier(POOL_DEBIAN),
                  pubconf.poolroot, logging.getLogger("DiskPool"))
    # Set the diskpool's log level to INFO to suppress debug output
    dp.logger.setLevel(20)
    dp.scan()

    log.debug("Preparing death row.")
    return DeathRow(distro, dp, log)

def main():
    parser = OptionParser()
    parser.add_option("-n", "--dry-run", action="store_true",
                      dest="dry_run", metavar="", default=False,
                      help=("Dry run: goes through the motions but "
                            "commits to nothing."))
    parser.add_option("-d", "--distribution",
                      dest="distribution", metavar="DISTRO",
                      help="Specified the distribution name.")

    logger_options(parser)
    (options, args) = parser.parse_args()
    log = logger(options, "deathrow-distro")

    log.debug("Initialising zopeless.")
    # XXX Change this when we fix up db security
    txn = initZopeless(dbuser='lucille')
    execute_zcml_for_scripts()

    distroname = options.distribution
    death_row = getDeathRow(distroname, log)
    try:
        # Unpublish death row
        log.debug("Unpublishing death row.")
        death_row.reap(options.dry_run)

        log.debug("Committing")
        if options.dry_run:
            txn.commit()
        else:
            txn.abort()
    except:
        log.exception("Bad muju while doing death-row unpublish")
        txn.abort()
        raise

if __name__ == "__main__":
    main()

