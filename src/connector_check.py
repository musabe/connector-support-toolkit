import sys
import argparse
from typing import List, Optional

from src.runner import CheckRunner
from src.reporter import Reporter


def _check_dependencies(db_type: str) -> None:
    if db_type == 'postgres':
        if sys.modules.get('psycopg2') is None:
            print('Error: psycopg2 not installed. Run: pip install psycopg2-binary')
            sys.exit(1)
        try:
            import psycopg2  # noqa: F401
        except ImportError:
            print('Error: psycopg2 not installed. Run: pip install psycopg2-binary')
            sys.exit(1)
    elif db_type == 'mysql':
        try:
            import mysql.connector  # noqa: F401
        except ImportError:
            print('Error: mysql-connector-python not installed. Run: pip install mysql-connector-python')
            sys.exit(1)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description='Validate database connector readiness')
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--db', required=True)
    parser.add_argument('--user', required=True)
    parser.add_argument('--password', required=True)
    parser.add_argument('--db-type', required=True, choices=['postgres', 'mysql'])
    parser.add_argument('--output-file', default=None)
    parser.add_argument('--skip', default='')
    args = parser.parse_args(argv)

    skip = [s.strip() for s in args.skip.split(',') if s.strip()]

    _check_dependencies(args.db_type)

    runner = CheckRunner(args.db_type, args.host, args.port, args.db, args.user, args.password, skip=skip)
    reporter = Reporter()

    results = runner.run()
    reporter.print_terminal(results)

    if args.output_file:
        reporter.write_json(results, host=args.host, db_type=args.db_type, output_file=args.output_file)


if __name__ == '__main__':
    main()
