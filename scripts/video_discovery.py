"""Compatibility imports for MCP scripts; the API shares the same flow contract."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "providers"))
from stepcheck_providers.flow import DetectedAction, Detection, build_flow  # noqa: E402,F401
