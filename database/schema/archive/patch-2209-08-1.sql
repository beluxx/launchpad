-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE Product DROP CONSTRAINT private_bugs_need_contact;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 08, 1);


