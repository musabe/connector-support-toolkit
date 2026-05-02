import json
import os
import tempfile
from io import StringIO

from rich.console import Console

from src.models import CheckResult
from src.reporter import Reporter


def _reporter_with_buffer():
    buf = StringIO()
    reporter = Reporter(console=Console(file=buf, highlight=False))
    return reporter, buf


def test_terminal_output_shows_category_header():
    reporter, buf = _reporter_with_buffer()
    reporter.print_terminal([CheckResult('connectivity', 'TCP reachability', 'PASS', 'host=localhost')])
    assert 'CONNECTIVITY' in buf.getvalue()


def test_terminal_output_shows_check_name_and_status():
    reporter, buf = _reporter_with_buffer()
    reporter.print_terminal([CheckResult('connectivity', 'TCP reachability', 'PASS', 'host=localhost')])
    output = buf.getvalue()
    assert 'PASS' in output
    assert 'TCP reachability' in output


def test_terminal_output_groups_by_category():
    reporter, buf = _reporter_with_buffer()
    results = [
        CheckResult('connectivity', 'TCP reachability', 'PASS', ''),
        CheckResult('connectivity', 'SSL', 'PASS', ''),
        CheckResult('permissions', 'Replication', 'WARN', ''),
    ]
    reporter.print_terminal(results)
    output = buf.getvalue()
    assert output.index('CONNECTIVITY') < output.index('PERMISSIONS')


def test_json_report_structure():
    reporter, _ = _reporter_with_buffer()
    results = [
        CheckResult('connectivity', 'TCP reachability', 'PASS', 'host=localhost'),
        CheckResult('cdc', 'wal_level', 'FAIL', 'found: replica'),
    ]
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        path = f.name
    try:
        reporter.write_json(results, host='localhost', db_type='postgres', output_file=path)
        with open(path) as f:
            report = json.load(f)
        assert report['host'] == 'localhost'
        assert report['db_type'] == 'postgres'
        assert report['summary']['passed'] == 1
        assert report['summary']['failed'] == 1
        assert report['summary']['warned'] == 0
        assert len(report['checks']) == 2
        assert 'timestamp' in report
    finally:
        os.unlink(path)
