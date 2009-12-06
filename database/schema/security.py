#!/usr/bin/python2.5
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

# pylint: disable-msg=W0403
import _pythonpath

from itertools import chain
import os
import sets
import sys

import psycopg2

from ConfigParser import SafeConfigParser
from optparse import OptionParser
from fti import quote_identifier
from canonical.database.sqlbase import connect
from canonical.launchpad.scripts import logger_options, logger, db_options
import replication.helpers


# The 'read' group does not get given select permission on the following
# tables. This is to stop the ro user being given access to secrurity
# sensitive information that interactive sessions don't need.
SECURE_TABLES = [
    'public.accountpassword',
    ]


class DbObject(object):
    def __init__(
            self, schema, name, type_, owner, arguments=None, language=None):
        self.schema = schema
        self.name = name
        self.type = type_
        self.owner = owner
        self.arguments = arguments
        self.language = language

    def __eq__(self, other):
        return self.schema == other.schema and self.name == other.name

    @property
    def fullname(self):
        fn = "%s.%s" % (
                self.schema, self.name
                )
        if self.type == 'function':
            fn = "%s(%s)" % (fn, self.arguments)
        return fn

    @property
    def seqname(self):
        if self.type != 'table':
            return ''
        return "%s.%s" % (self.schema, self.name + '_id_seq')


class DbSchema(dict):
    groups = None # List of groups defined in the db
    users = None # List of users defined in the db
    def __init__(self, con):
        super(DbSchema, self).__init__()
        cur = con.cursor()
        cur.execute('''
            SELECT
                n.nspname as "Schema",
                c.relname as "Name",
                CASE c.relkind
                    WHEN 'r' THEN 'table'
                    WHEN 'v' THEN 'view'
                    WHEN 'i' THEN 'index'
                    WHEN 'S' THEN 'sequence'
                    WHEN 's' THEN 'special'
                END as "Type",
                u.usename as "Owner"
            FROM pg_catalog.pg_class c
                LEFT JOIN pg_catalog.pg_user u ON u.usesysid = c.relowner
                LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r','v','S','')
                AND n.nspname NOT IN ('pg_catalog', 'pg_toast')
                AND pg_catalog.pg_table_is_visible(c.oid)
            ORDER BY 1,2
            ''')
        for schema, name, type_, owner in cur.fetchall():
            key = '%s.%s' % (schema, name)
            self[key] = DbObject(schema, name, type_, owner)

        cur.execute(r"""
            SELECT
                n.nspname as "schema",
                p.proname as "name",
                pg_catalog.oidvectortypes(p.proargtypes) as "Argument types",
                u.usename as "owner",
                l.lanname as "language"
            FROM pg_catalog.pg_proc p
                LEFT JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                LEFT JOIN pg_catalog.pg_language l ON l.oid = p.prolang
                LEFT JOIN pg_catalog.pg_user u ON u.usesysid = p.proowner
                LEFT JOIN pg_catalog.pg_type r ON r.oid = p.prorettype
            WHERE
                r.typname NOT IN ('trigger', 'language_handler')
                AND pg_catalog.pg_function_is_visible(p.oid)
                AND n.nspname <> 'pg_catalog'
                """)
        for schema, name, arguments, owner, language in cur.fetchall():
            self['%s.%s(%s)' % (schema, name, arguments)] = DbObject(
                    schema, name, 'function', owner, arguments, language
                    )
        # Pull a list of groups
        cur.execute("SELECT groname FROM pg_group")
        self.groups = [r[0] for r in cur.fetchall()]

        # Pull a list of users
        cur.execute("SELECT usename FROM pg_user")
        self.users = [r[0] for r in cur.fetchall()]

    @property
    def principals(self):
        return chain(self.groups, self.users)


class CursorWrapper(object):
    def __init__(self, cursor):
        self.__dict__['_cursor'] = cursor

    def execute(self, cmd, params=None):
        cmd = cmd.encode('utf8')
        if params is None:
            log.debug('%s' % (cmd, ))
            return self.__dict__['_cursor'].execute(cmd)
        else:
            log.debug('%s [%r]' % (cmd, params))
            return self.__dict__['_cursor'].execute(cmd, params)

    def __getattr__(self, key):
        return getattr(self.__dict__['_cursor'], key)

    def __setattr__(self, key, value):
        return setattr(self.__dict__['_cursor'], key, value)


CONFIG_DEFAULTS = {
    'groups': ''
    }


def main(options):
    # Load the config file
    config = SafeConfigParser(CONFIG_DEFAULTS)
    configfile_name = os.path.join(os.path.dirname(__file__), 'security.cfg')
    config.read([configfile_name])

    con = connect(options.dbuser)
    cur = CursorWrapper(con.cursor())

    if options.cluster:
        nodes = replication.helpers.get_nodes(con, 1)
        if nodes:
            # If we have a replicated environment, reset permissions on all
            # Nodes.
            con.close()
            for node in nodes:
                log.info("Resetting permissions on %s (%s)" % (
                    node.nickname, node.connection_string))
                reset_permissions(
                    psycopg2.connect(node.connection_string), config, options)
        else:
            log.error("--cluster requested, but not a Slony-I cluster.")
            return 1
    else:
        log.info("Resetting permissions on single database")
        reset_permissions(con, config, options)


def reset_permissions(con, config, options):
    schema = DbSchema(con)
    cur = CursorWrapper(con.cursor())

    # Add our two automatically maintained groups
    for group in ['read', 'admin']:
        if group in schema.principals:
            for user in schema.users:
                cur.execute("ALTER GROUP %s DROP USER %s" % (
                    quote_identifier(group), quote_identifier(user)
                    ))
        else:
            cur.execute("CREATE GROUP %s" % quote_identifier(group))
            schema.groups.append(group)

    # Create all required groups and users.
    for section_name in config.sections():
        if section_name.lower() == 'public':
            continue

        assert not section_name.endswith('_ro'), (
            '_ro namespace is reserved (%s)' % repr(section_name))

        type_ = config.get(section_name, 'type')
        assert type_ in ['user', 'group'], 'Unknown type %s' % type_

        role_options = [
            'NOCREATEDB', 'NOCREATEROLE', 'NOCREATEUSER', 'INHERIT']
        if type_ == 'user':
            role_options.append('LOGIN')
        else:
            role_options.append('NOLOGIN')

        for username in [section_name, '%s_ro' % section_name]:
            if username in schema.principals:
                if type_ == 'group':
                    for member in schema.users:
                        cur.execute(
                            "REVOKE %s FROM %s" % (
                                quote_identifier(username),
                                quote_identifier(member)))
                else:
                    # Note - we don't drop the user because it might own
                    # objects in other databases. We need to ensure they are
                    # not superusers though!
                    cur.execute(
                        "ALTER ROLE %s WITH %s" % (
                            quote_identifier(username),
                            ' '.join(role_options)))
            else:
                cur.execute(
                    "CREATE ROLE %s WITH %s"
                    % (quote_identifier(username), ' '.join(role_options)))
                schema.groups.append(username)

        # Set default read-only mode for our roles.
        cur.execute(
            'ALTER ROLE %s SET default_transaction_read_only TO FALSE'
            % quote_identifier(section_name))
        cur.execute(
            'ALTER ROLE %s SET default_transaction_read_only TO TRUE'
            % quote_identifier('%s_ro' % section_name))

    # Add users to groups
    for user in config.sections():
        if config.get(user, 'type') != 'user':
            continue
        groups = [
            g.strip() for g in config.get(user, 'groups', '').split(',')
            if g.strip()
            ]
        # Read-Only users get added to Read-Only groups.
        if user.endswith('_ro'):
            groups = ['%s_ro' % group for group in groups]
        for group in groups:
            cur.execute(r"""ALTER GROUP %s ADD USER %s""" % (
                quote_identifier(group), quote_identifier(user)
                ))

    # Change ownership of all objects to OWNER
    for obj in schema.values():
        if obj.type in ("function", "sequence"):
            pass # Can't change ownership of functions or sequences
        else:
            cur.execute("ALTER TABLE %s OWNER TO %s" % (
                obj.fullname, quote_identifier(options.owner)
                ))

    # Revoke all privs from known groups. Don't revoke anything for
    # users or groups not defined in our security.cfg.
    for section_name in config.sections():
        for obj in schema.values():
            if obj.type == 'function':
                t = 'FUNCTION'
            else:
                t = 'TABLE'

            roles = [quote_identifier(section_name)]
            if section_name != 'public':
                roles.append(quote_identifier(section_name + '_ro'))
            for role in roles:
                cur.execute(
                    'REVOKE ALL ON %s %s FROM %s' % (t, obj.fullname, role))
                if schema.has_key(obj.seqname):
                    cur.execute(
                        'REVOKE ALL ON SEQUENCE %s FROM %s'
                        % (obj.seqname, role))

    # Set of all tables we have granted permissions on. After we have assigned
    # permissions, we can use this to determine what tables have been
    # forgotten about.
    found = sets.Set()

    # Set permissions as per config file
    for username in config.sections():
        for obj_name, perm in config.items(username):
            if '.' not in obj_name:
                continue
            if obj_name not in schema.keys():
                log.warn('Bad object name %r', obj_name)
                continue
            obj = schema[obj_name]

            found.add(obj)

            perm = perm.strip()
            if not perm:
                # No perm means no rights. We can't grant no rights, so skip.
                continue

            who = quote_identifier(username)
            if username == 'public':
                who_ro = who
            else:
                who_ro = quote_identifier('%s_ro' % username)

            if obj.type == 'function':
                cur.execute(
                    'GRANT %s ON FUNCTION %s TO %s'
                    % (perm, obj.fullname, who))
                cur.execute(
                    'GRANT EXECUTE ON FUNCTION %s TO GROUP read'
                    % obj.fullname)
                cur.execute(
                    'GRANT ALL ON FUNCTION %s TO GROUP admin'
                    % obj.fullname)
                cur.execute(
                    'GRANT EXECUTE ON FUNCTION %s TO GROUP %s'
                    % (obj.fullname, who_ro))
            else:
                cur.execute(
                    'GRANT %s ON TABLE %s TO %s'
                    % (perm, obj.fullname, who))
                if obj.fullname not in SECURE_TABLES:
                    cur.execute(
                        'GRANT SELECT ON TABLE %s TO GROUP read'
                        % obj.fullname)
                cur.execute(
                    'GRANT ALL ON TABLE %s TO GROUP admin'
                    % obj.fullname)
                cur.execute(
                    'GRANT SELECT ON TABLE %s TO %s'
                    % (obj.fullname, who_ro))
                if schema.has_key(obj.seqname):
                    if 'INSERT' in perm:
                        seqperm = 'USAGE'
                    elif 'SELECT' in perm:
                        seqperm = 'SELECT'
                    cur.execute(
                        'GRANT %s ON %s TO %s'
                        % (seqperm, obj.seqname, who))
                    if obj.fullname not in SECURE_TABLES:
                        cur.execute(
                            'GRANT SELECT ON %s TO GROUP read'
                            % obj.seqname)
                    cur.execute(
                        'GRANT ALL ON %s TO GROUP admin'
                        % obj.seqname)
                    cur.execute(
                        'GRANT SELECT ON %s TO %s'
                        % (obj.seqname, who_ro))

    # Set permissions on public schemas
    public_schemas = [
        s.strip() for s in config.get('DEFAULT','public_schemas').split(',')
        if s.strip()
        ]
    for schema_name in public_schemas:
        cur.execute("GRANT USAGE ON SCHEMA %s TO PUBLIC" % (
            quote_identifier(schema_name),
            ))
    for obj in schema.values():
        if obj.schema not in public_schemas:
            continue
        found.add(obj)
        if obj.type == 'function':
            cur.execute('GRANT EXECUTE ON FUNCTION %s TO PUBLIC' %
                        obj.fullname)
        else:
            cur.execute('GRANT SELECT ON TABLE %s TO PUBLIC' % obj.fullname)

    # Raise an error if we have database objects lying around that have not
    # had permissions assigned.
    forgotten = sets.Set()
    for obj in schema.values():
        if obj not in found:
            forgotten.add(obj)
    forgotten = [obj.fullname for obj in forgotten
        if obj.type in ['table','function','view']]
    if forgotten:
        log.warn('No permissions specified for %r', forgotten)

    con.commit()


if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option(
        "-o", "--owner", dest="owner", default="postgres",
        help="Owner of PostgreSQL objects")
    parser.add_option(
        "-c", "--cluster", dest="cluster", default=False,
        action="store_true",
        help="Rebuild permissions on all nodes in the Slony-I cluster.")
    db_options(parser)
    logger_options(parser)

    (options, args) = parser.parse_args()

    log = logger(options)

    sys.exit(main(options))
