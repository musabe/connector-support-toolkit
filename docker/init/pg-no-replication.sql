-- Scenario: pg-no-replication
-- Creates a user with connect access but no REPLICATION privilege

CREATE USER norepl WITH PASSWORD 'norepl';
GRANT CONNECT ON DATABASE test TO norepl;
GRANT USAGE ON SCHEMA public TO norepl;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO norepl;

-- Deliberately NOT granting: ALTER ROLE norepl REPLICATION;
-- This is the misconfiguration being tested.
