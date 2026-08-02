-- Runs once, on an empty data directory. The suite owns this database and recreates its
-- schema on every session, so it must not be the one holding demo data.
CREATE DATABASE tokokita_test OWNER tokokita;
