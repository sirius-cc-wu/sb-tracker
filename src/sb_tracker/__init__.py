"""
Simple Beads (sb) - A minimal, standalone issue tracker for individuals.
No git hooks, no complex dependencies, just one local SQLite file.
"""

__version__ = "0.4.0"
__author__ = "Simple Beads Contributors"

from .cli import main

__all__ = ["main"]
