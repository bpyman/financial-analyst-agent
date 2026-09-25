"""The README describes the Next.js window, and its media come from the capture script.

Ticket 12, ADR 0006 cutover criteria: the portfolio images are re-captured from the
new window by ``web/scripts/capture-portfolio.ts``, so they can be regenerated
whenever the window changes, and the README drops the Streamlit run instructions.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
IMAGES = ROOT / "docs" / "portfolio" / "images"
CAPTURE_SCRIPT = ROOT / "web" / "scripts" / "capture-portfolio.ts"
ADR_0006 = "docs/adr/0006-react-audience-window.md"
# Until ticket 11 records the hosted URL, the README carries this marker instead.
HOSTED_URL_PLACEHOLDER = "HOSTED_DEMO_URL"


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _readme_media() -> set[str]:
    return set(re.findall(r"docs/portfolio/images/([\w.-]+)", _readme()))


def test_readme_media_exist() -> None:
    media = _readme_media()
    assert {"demo-walkthrough.gif", "demo-walkthrough.mp4"} <= media
    missing = sorted(name for name in media if not (IMAGES / name).is_file())
    assert missing == []


def test_capture_script_writes_every_portfolio_image() -> None:
    script = CAPTURE_SCRIPT.read_text(encoding="utf-8")
    on_disk = {path.name for path in IMAGES.iterdir() if path.is_file()}
    not_captured = sorted(name for name in on_disk | _readme_media() if f'"{name}"' not in script)
    assert not_captured == []


def test_readme_has_no_streamlit_instructions() -> None:
    assert "streamlit" not in _readme().lower()


def test_readme_links_adr_0006() -> None:
    assert f"]({ADR_0006})" in _readme()


def test_readme_names_the_hosted_demo_or_its_placeholder() -> None:
    text = _readme()
    hosted = re.search(r"https://[\w-]+\.vercel\.app", text)
    assert hosted or HOSTED_URL_PLACEHOLDER in text
