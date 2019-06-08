-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE archive ADD COLUMN publish_debug_symbols boolean;
ALTER TABLE archive ALTER COLUMN publish_debug_symbols SET DEFAULT false;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 45, 0);
