#!/usr/bin/env python3
"""Create the Quinovo eval-failure Langfuse dataset and experiment rule."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quinovo.llm.eval_dataset import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
