"""The recorded runtime's SEC cassette holds every concept the metric catalog reads."""

from __future__ import annotations

import json

from financial_analyst_agent.facts import _RECORDING_PATH
from financial_analyst_agent.services.metric_catalog import READ_CONCEPTS


def test_the_cassette_was_recorded_with_every_concept_the_catalog_reads() -> None:
    cassette = json.loads(_RECORDING_PATH.read_text(encoding="utf-8"))
    recorded = set(cassette.get("read_concepts", ()))
    read = {f"{taxonomy}:{concept}" for taxonomy, concept in READ_CONCEPTS}

    # A concept the catalog reads but the cassette never asked SEC for makes the
    # recorded runtime refuse a figure the live one shows (Amgen's R&D, bank revenue).
    missing = sorted(read - recorded)
    assert not missing, f"Re-record with scripts/record_sec_fixtures.py; it lacks {missing}"
