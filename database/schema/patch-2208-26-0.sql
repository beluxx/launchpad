-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

CREATE INDEX productseries_name_sort
ON ProductSeries
USING btree (version_sort_key(name));

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 26, 0);
