-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE BugNotification
    ADD COLUMN activity INTEGER REFERENCES BugActivity;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 46, 0);
