"""OpenAI essay completion for qualitative live turns."""

import json
from typing import Any

from financial_analyst_agent.config import Settings
from financial_analyst_agent.planner import openai_client_from_settings

_EXPLAIN_INSTRUCTIONS = (
    "Write a concise financial-analyst essay that answers the user's question. "
    "Do not include numeric tokens because ungrounded numerals are rejected downstream."
)
_ANALYSIS_INSTRUCTIONS = (
    "Write a concise financial-analyst essay that answers the user's question. "
    "You may quote numeric values that appear in the supplied analysis JSON. "
    "Do not invent numerals that are absent from that JSON."
)
_NEWS_INSTRUCTIONS = (
    "Write a concise financial-analyst brief using only the supplied news tool JSON. "
    "Cite sources only as [n], where n is the 1-based index of an object in that JSON array. "
    "Do not write (n), n., [1, 2], or [1-3]. "
    "Do not introduce facts or numeric tokens that are absent from that JSON, "
    "except those [n] markers."
)


def _is_news_tool_json(tool_json: str) -> bool:
    try:
        payload = json.loads(tool_json)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, list) or not payload:
        return False
    first = payload[0]
    return isinstance(first, dict) and "url" in first and "title" in first


class OpenAIEssayCompleter:
    """Generate qualitative essays through the OpenAI Responses API."""

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAIEssayCompleter":
        return cls(*openai_client_from_settings(settings))

    def complete_essay(self, query: str, tool_json: str = "") -> str:
        instructions = _EXPLAIN_INSTRUCTIONS
        input_text = query
        if _is_news_tool_json(tool_json):
            instructions = _NEWS_INSTRUCTIONS
            input_text = f"User query:\n{query}\n\nNews tool JSON:\n{tool_json}"
        elif tool_json:
            instructions = _ANALYSIS_INSTRUCTIONS
            input_text = f"{query}\n\nAnalysis JSON:\n{tool_json}"
        response = self._client.responses.create(
            model=self._model,
            instructions=instructions,
            input=input_text,
        )
        return str(response.output_text)
