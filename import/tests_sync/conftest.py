"""Pytest config for sync tests.

Adds `import/` to sys.path so `from pioblog_sync.<module> import ...`
and `from lib.<module> import ...` both work.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
