#!/usr/bin/python2.4
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bring a new slave online."""

__metaclass__ = type
__all__ = []

import _pythonpath

from optparse import OptionParser
import subprocess
import sys
import time
from textwrap import dedent

import psycopg2

from canonical.database.postgresql import ConnectionString
from canonical.database.sqlbase import (
    connect_string, ISOLATION_LEVEL_AUTOCOMMIT)
from canonical.launchpad.scripts import db_options, logger_options, logger
from canonical.launchpad.webapp.adapter import _auth_store_tables

import replication.helpers
from replication.helpers import AUTHDB_SET_ID, LPMAIN_SET_ID

def main():
    parser = OptionParser(
        "Usage: %prog [options] node_id connection_string")

    db_options(parser)
    logger_options(parser)

    options, args = parser.parse_args()

    log = logger(options, 'new-slave')

    if len(args) != 2:
        parser.error("Missing required arguments.")

    node_id, raw_target_connection_string = args

    # Confirm we can connect to the source database.
    # Keep the connection as we need it later.
    source_connection_string = ConnectionString(connect_string('slony'))
    try:
        log.debug(
            "Opening source connection to '%s'" % source_connection_string)
        source_connection = psycopg2.connect(str(source_connection_string))
        source_connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    except psycopg2.Error, exception:
        parser.error("Unable to connect as %s (%s)" % (
            source_connection_string, str(exception).strip()))

    # Confirm we are connected to a Slony-I node.
    if not replication.helpers.slony_installed(source_connection):
        parser.error(
            "Database at %s is not a Slony-I node."
            % source_connection_string)

    # Sanity check the given node_id.
    existing_nodes = replication.helpers.get_all_cluster_nodes(
        source_connection)
    try:
        node_id = int(node_id)
    except ValueError:
        parser.error("node_id must be a positive integer.")
    if node_id <= 0:
        parser.error("node_id must be a positive integer.")

    if node_id in [node.node_id for node in existing_nodes]:
        parser.error("Node %d already exists in the cluster." % node_id)

    # Get the connection string for masters.
    lpmain_connection_string = get_master_connection_string(
        source_connection, parser, AUTHDB_SET_ID) or source_connection_string
    authdb_connection_string = get_master_connection_string(
        source_connection, parser, LPMAIN_SET_ID) or source_connection_string

    # Sanity check the target connection string.
    target_connection_string = ConnectionString(raw_target_connection_string)
    if target_connection_string.user is None:
        target_connection_string.user = 'slony'

    # Make sure we can connect as the required users to our target.
    # Keep the connection as we need it.
    try:
        target_con = psycopg2.connect(str(target_connection_string))
    except psycopg2.Error, exception:
        parser.error("Failed to connect using '%s' (%s)" % (
            target_connection_string, str(exception).strip()))

    # Confirm the target database is sane. Check for common errors
    # that people might make when bringing new replicas online at 4am.
    cur = target_con.cursor()
    cur.execute("SHOW lc_collate")
    collation = cur.fetchone()[0]
    if collation != "C":
        parser.error(
            "Database at %s has incorrect collation (%s)" % (
                target_connection_string, collation))
    cur.execute("SHOW server_encoding")
    encoding = cur.fetchone()[0]
    if encoding != "UTF8":
        parser.error(
            "Database at %s has incorrect encoding (%s)" % (
                target_connection_string, encoding))
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
        """)
    num_existing_objects = cur.fetchone()[0]
    if num_existing_objects != 0:
        parser.error(
            "Database at %s is not empty." % target_connection_string)
    target_con.rollback()

    # Duplicate the full schema. We restore with no-privileges as required
    # roles may not yet exist, so we have to run security.py on the
    # new slave once it is built.
    log.info("Duplicating full db schema from '%s' to '%s'" % (
        lpmain_connection_string, target_connection_string))
    cmd = "pg_dump --schema-only --no-privileges %s | psql -1 -q %s" % (
        source_connection_string.asPGCommandLineArgs(),
        target_connection_string.asPGCommandLineArgs())
    if subprocess.call(cmd, shell=True) != 0:
        log.error("Failed to duplicate database schema.")
        return 1

    # Drop the authdb replication set tables we just restored, as they
    # will be broken if the authdb master is a seperate database to the
    # lpmain master.
    log.debug("Dropping (possibly corrupt) authdb tables.")
    cur = target_con.cursor()
    for table_name in _auth_store_tables:
        cur.execute("DROP TABLE IF EXISTS %s CASCADE" % table_name)
    target_con.commit()

    # Duplicate the authdb schema.
    log.info("Duplicating authdb schema from '%s' to '%s'" % (
        authdb_connection_string, target_connection_string))
    table_args = ["--table=%s" % table for table in _auth_store_tables]
    # We need to restore the two cross-replication-set views that where
    # dropped as a side effect of dropping the auth store tables.
    table_args.append("--table=ValidPersonCache")
    table_args.append("--table=ValidPersonOrTeamCache")
    cmd = "pg_dump --schema-only --no-privileges %s %s | psql -1 -q %s" % (
        ' '.join(table_args),
        source_connection_string.asPGCommandLineArgs(),
        target_connection_string.asPGCommandLineArgs())
    if subprocess.call(cmd, shell=True) != 0:
        log.error("Failed to duplicate database schema.")
        return 1

    # Trash the broken Slony tables we just duplicated.
    log.debug("Removing slony cruft.")
    cur = target_con.cursor()
    cur.execute("DROP SCHEMA _sl CASCADE")
    target_con.commit()
    del target_con

    # Get a list of existing set ids.
    source_connection.rollback()
    master_node = replication.helpers.get_master_node(source_connection)
    cur = source_connection.cursor()
    cur.execute(
        "SELECT set_id FROM _sl.sl_set WHERE set_origin=%d"
        % master_node.node_id)
    set_ids = [set_id for set_id, in cur.fetchall()]
    log.debug("Discovered set ids %s" % repr(list(set_ids)))

    # Generate and run a slonik(1) script to initialize the new node
    # and subscribe it to our replication sets.
    comment = 'New node created %s' % time.ctime()
    script = dedent("""\
        define new_node %d;
        define new_node_conninfo '%s';
        node @new_node admin conninfo = @new_node_conninfo;

        echo 'Initializing new node.';
        try {
            store node (id=@new_node, comment='%s');
            echo 'Creating new node paths.';
        """ % (node_id, target_connection_string, comment))

    for node in existing_nodes:
        script += dedent("""\
            store path (
                server=@%(nickname)s, client=@new_node,
                conninfo=@%(nickname)s_conninfo);
            store path (
                server=@new_node, client=@%(nickname)s,
                conninfo=@new_node_conninfo);
            """ % {'nickname': node.nickname})

    script += dedent("""\
        } on error { echo 'Failed.'; exit 1; }
        """)

    for set_id in set_ids:

        script += dedent("""\
        echo 'Subscribing new node to set %d.';
        subscribe set (
            id=%d, provider=@master_node, receiver=@new_node, forward=yes);

        echo 'Waiting for sync... this might take a while...';
        sync (id = @master_node);
        wait for event (
            origin = ALL, confirmed = ALL,
            wait on = @master_node, timeout = 0);
        """ % (set_id, set_id))

    replication.helpers.execute_slonik(script)

    replication.helpers.validate_replication(source_connection.cursor())

    return 0


def get_master_connection_string(con, parser, set_id):
    """Return the connection string to the origin for the replication set.
    """
    cur = con.cursor()
    cur.execute("""
        SELECT pa_conninfo FROM _sl.sl_set, _sl.sl_path
        WHERE set_origin = pa_server AND set_id = %d
        LIMIT 1
        """ % set_id)
    row = cur.fetchone()
    if row is None:
        # If we have no paths stored, there is only a single node in the
        # cluster.
        return None
    else:
        connection_string = ConnectionString(row[0])

    # Confirm we can connect from here.
    try:
        test_con = psycopg2.connect(str(connection_string))
    except psycopg2.Error, exception:
        parser.error("Failed to connect to using '%s' (%s)" % (
            connection_string, str(exception).strip()))

    return connection_string


if __name__ == '__main__':
    sys.exit(main())
