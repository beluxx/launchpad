SET client_min_messages=ERROR;
ALTER TABLE BugWatch ADD COLUMN lasterror integer;
INSERT INTO LaunchpadDatabaseRevision VALUES (87, 99, 0);
