from __future__ import annotations

import json
import sys

from ..models import RunReport
from .base import BaseReporter


class JsonReporter(BaseReporter):
    reporter_type = "json"

    def report(self, run: RunReport) -> None:
        payload = json.dumps(run.to_dict(), indent=2)
        output_file = run.config.output_file

        if output_file:
            with open(output_file, "w") as f:
                f.write(payload)
            print(f"Report written to {output_file}")
        else:
            sys.stdout.write(payload + "\n")
