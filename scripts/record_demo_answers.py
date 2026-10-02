"""Write web/lib/demo-answers.json: each guided story's answer on the recorded runtime.

While the hosted API wakes (about a minute on a sleeping free tier), the window
shows a clicked story's recorded answer at once, labelled "Demo data", then the
live one when it lands. The answers come from the same recorded runtime and
presentation code the API serves, so they say nothing the API would not;
tests/unit/test_demo_answers.py fails when the file drifts from a fresh run.

Usage: uv run python scripts/record_demo_answers.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from financial_analyst_agent.api import presentation_json
from financial_analyst_agent.conversation import run_conversation_turn
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.storefront import GUIDED_STORIES
from financial_analyst_agent.thread_store import LocalThreadStore

OUT = Path(__file__).resolve().parent.parent / "web/lib/demo-answers.json"


def demo_answers() -> dict[str, Any]:
    """Each guided story's presentation, as the API would serialise it."""
    runtime = recorded_runtime()
    stories = []
    with tempfile.TemporaryDirectory() as folder:
        store = LocalThreadStore(Path(folder))
        for index, (label, question) in enumerate(GUIDED_STORIES):
            turn = run_conversation_turn(f"demo-{index}", question, runtime, store=store)
            stories.append(
                {
                    "label": label,
                    "question": question,
                    "presentation": presentation_json(turn.result),
                }
            )
    return {"source": "scripts/record_demo_answers.py (recorded runtime)", "stories": stories}


def render(answers: dict[str, Any]) -> str:
    return json.dumps(answers, ensure_ascii=False, indent=1, default=str) + "\n"


if __name__ == "__main__":
    OUT.write_text(render(demo_answers()), encoding="utf-8")
    print(f"{len(GUIDED_STORIES)} story answers -> {OUT}")
