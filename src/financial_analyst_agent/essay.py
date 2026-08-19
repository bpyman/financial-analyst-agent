"""OpenAI essay completion for qualitative live turns."""

from typing import Any

from financial_analyst_agent.config import Settings
from financial_analyst_agent.planner import openai_client_from_settings

_EXPLAIN_INSTRUCTIONS = (
    "Write a concise financial-analyst essay that answers the user's question. "
    "Do not include numeric tokens because ungrounded numerals are rejected downstream."
)
_NEWS_INSTRUCTIONS = (
    "Write a concise financial-analyst brief using only the supplied news tool JSON. "
    "Do not introduce facts or numeric tokens that are absent from that JSON."
)


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
        if tool_json:
            instructions = _NEWS_INSTRUCTIONS
            input_text = f"User query:\n{query}\n\nNews tool JSON:\n{tool_json}"
        response = self._client.responses.create(
            model=self._model,
            instructions=instructions,
            input=input_text,
        )
        return str(response.output_text)
