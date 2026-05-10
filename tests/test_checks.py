# This file previously served as a test index.
# Tests are now organised by module:
#
#   tests/test_models.py            — CheckResult dataclass, BaseConnector ABC
#   tests/test_reporter.py          — TerminalReporter, JsonReporter
#   tests/test_runner.py            — runner orchestration, exit codes
#   tests/test_cli.py               — CLI arg parsing, main() integration
#   tests/test_postgres_checker.py  — PostgresConnector (mocked psycopg2)
#   tests/test_mysql_checker.py     — MySQLConnector (mocked mysql.connector)
#   tests/test_mongo.py             — MongoConnector (mocked pymongo)
#   tests/test_config.py            — YAML config loader, env-var interpolation
#   tests/test_exit_codes.py        — exit_code() all four paths
