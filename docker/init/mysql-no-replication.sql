-- Scenario: mysql-no-replication
-- Creates a user with SELECT access but no REPLICATION SLAVE privilege

CREATE USER 'norepl'@'%' IDENTIFIED BY 'norepl';
GRANT SELECT ON test.* TO 'norepl'@'%';
-- Also grant full access to demo user
GRANT ALL PRIVILEGES ON test.* TO 'demo'@'%';
GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'demo'@'%';
FLUSH PRIVILEGES;

-- Deliberately NOT granting REPLICATION SLAVE to norepl.
-- This is the misconfiguration being tested.
