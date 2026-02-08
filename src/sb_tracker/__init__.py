"""
Simple Beads (sb) - A minimal, standalone issue tracker for individuals.
No git hooks, no complex dependencies, just one JSON file.
"""

__version__ = "0.1.1"
__author__ = "Simple Beads Contributors"

from .cli import main

__all__ = ["main"]
