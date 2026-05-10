"""
Backward-compatibility shim.

All existing invocations of:
    python -m src.connector_check --host ...

continue to work unchanged. This file is intentionally minimal.
"""
from connector_toolkit.cli import main

if __name__ == "__main__":
    main()
