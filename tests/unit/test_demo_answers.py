"""The window's cold-start story answers stay what the recorded runtime says."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_committed_demo_answers_match_a_fresh_recorded_run() -> None:
    spec = importlib.util.spec_from_file_location(
        "record_demo_answers", ROOT / "scripts/record_demo_answers.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    committed = (ROOT / "web/lib/demo-answers.json").read_text(encoding="utf-8")
    # Regenerate with: uv run python scripts/record_demo_answers.py
    assert module.render(module.demo_answers()) == committed
