"""CLI event handler — re-exports CliEventHandler from display module.

This module exists for backward compatibility. The actual implementation
lives in display.py.
"""

from .display import CliEventHandler

__all__ = ["CliEventHandler"]
