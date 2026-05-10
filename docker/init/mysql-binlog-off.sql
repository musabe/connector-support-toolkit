-- Scenario: mysql-binlog-off
-- Full grants but binary logging is disabled at the server level
GRANT ALL PRIVILEGES ON test.* TO 'demo'@'%';
GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'demo'@'%';
FLUSH PRIVILEGES;
