-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE Packageset RENAME COLUMN score TO relative_build_score;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 18, 4);
