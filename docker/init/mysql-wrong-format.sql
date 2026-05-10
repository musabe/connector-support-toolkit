-- Scenario: mysql-wrong-binlog-format
-- Full grants — the misconfiguration is binlog_format=STATEMENT at server level
GRANT ALL PRIVILEGES ON test.* TO 'demo'@'%';
GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'demo'@'%';
FLUSH PRIVILEGES;
