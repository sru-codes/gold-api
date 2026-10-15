"""Shared test fixtures.

Tests are hermetic: nothing here touches the network. Provider tests inject a
fake transport into ``JsonHttpClient``, so they run offline and deterministically.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the repository root importable so ``import app`` works without install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
