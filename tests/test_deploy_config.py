"""The checked-in deploy configuration (ticket 09, ADR 0006 "Hosting").

``render.yaml`` is checked against the fields in Render's Blueprint reference,
since the official JSON schema is not reachable offline. The public-demo
environment it declares is then run through the real API. The Vercel side is
``web/vercel.json`` plus the ignored-build script, which is run against a
throwaway git repository.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from api_server import serve, smoke
from financial_analyst_agent.api import HEALTH_PATH, create_app
from financial_analyst_agent.config import AppMode, Settings

ROOT = Path(__file__).resolve().parents[1]
RENDER_YAML = ROOT / "render.yaml"
VERCEL_JSON = ROOT / "web" / "vercel.json"
IGNORE_BUILD = ROOT / "web" / "scripts" / "ignore-build.sh"
PROXY_ROUTE = ROOT / "web" / "app" / "api" / "[...path]" / "route.ts"
CI_YAML = ROOT / ".github" / "workflows" / "ci.yml"

# Service fields from Render's Blueprint reference (render-oss/skills,
# render-blueprints/references/field-reference.md), so a misspelt field fails
# here rather than at Blueprint sync.
RENDER_SERVICE_FIELDS = {
    "name", "type", "runtime", "region", "plan", "branch", "rootDir",
    "buildCommand", "startCommand", "preDeployCommand", "autoDeployTrigger",
    "maxShutdownDelaySeconds", "healthCheckPath", "domains", "envVars",
    "buildFilter", "disk", "scaling", "numInstances", "registryCredential",
    "image", "dockerfilePath", "dockerContext", "dockerCommand", "previews",
}  # fmt: skip
RENDER_DEPRECATED_FIELDS = {"env", "autoDeploy", "previewsEnabled", "pullRequestPreviewsEnabled"}
RENDER_REGIONS = {"oregon", "ohio", "virginia", "frankfurt", "singapore"}
# Fluid compute on Vercel Hobby: 300 s default and maximum.
VERCEL_HOBBY_MAX_DURATION = 300


def _render_service() -> dict[str, Any]:
    blueprint = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    assert set(blueprint) == {"services"}
    services = blueprint["services"]
    assert len(services) == 1, "one API service; the window is on Vercel"
    service: dict[str, Any] = services[0]
    return service


def _render_env() -> dict[str, dict[str, Any]]:
    return {entry["key"]: entry for entry in _render_service()["envVars"]}


def test_render_blueprint_is_one_free_docker_web_service_in_virginia() -> None:
    service = _render_service()

    assert set(service) <= RENDER_SERVICE_FIELDS
    assert not set(service) & RENDER_DEPRECATED_FIELDS
    assert service["type"] == "web"
    assert service["runtime"] == "docker"
    assert service["plan"] == "free"
    assert service["region"] in RENDER_REGIONS
    assert service["region"] == "virginia"
    assert service["branch"] == "master"
    assert (ROOT / service["dockerfilePath"]).is_file()
    assert (ROOT / service["dockerContext"]).resolve() == ROOT
    assert service["healthCheckPath"] == HEALTH_PATH
    # One process: the file-backed thread store and per-thread turn lock need it.
    assert service["numInstances"] == 1


def test_render_deploys_only_after_github_checks_pass() -> None:
    assert _render_service()["autoDeployTrigger"] == "checksPass"


def test_render_rebuilds_only_for_files_the_image_is_built_from() -> None:
    paths = _render_service()["buildFilter"]["paths"]
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    copied = re.findall(r"^COPY (?!--from)(.+) \S+$", dockerfile, flags=re.MULTILINE)
    sources = [source for line in copied for source in line.split()]

    assert sources, "the Dockerfile copies something from the context"
    for source in [*sources, "Dockerfile", ".dockerignore"]:
        assert source in paths or f"{source}/**" in paths, source
    assert not any(path.startswith("web") for path in paths)


def test_render_env_is_the_public_demo_with_an_unsynced_proxy_token() -> None:
    env = _render_env()

    for key, entry in env.items():
        assert key.lower() in Settings.model_fields, f"{key} is not a setting"
        assert set(entry) in ({"key", "value"}, {"key", "sync"}), key
        if "value" in entry:
            assert isinstance(entry["value"], str), f"quote {key} so YAML keeps it a string"
    assert env["APP_MODE"]["value"] == "recorded"
    assert env["PUBLIC_DEMO"]["value"] == "true"
    assert env["DEMO_LIVE_SEC"]["value"] == "false"
    assert env["API_PROXY_TOKEN"] == {"key": "API_PROXY_TOKEN", "sync": False}
    # Render sets PORT itself; the image already listens on it.
    assert "PORT" not in env


@pytest.fixture
def render_api(tmp_path: Path) -> Iterator[str]:
    values = {
        key.lower(): entry["value"] for key, entry in _render_env().items() if "value" in entry
    }
    settings = Settings(
        **values,
        api_proxy_token="dashboard-secret",
        _env_file=None,  # type: ignore[call-arg]
    )
    assert settings.app_mode is AppMode.RECORDED
    assert settings.public_demo
    yield from serve(create_app(settings, store_root=tmp_path / "threads"))


def test_render_env_serves_the_guided_story_only_through_the_proxy(render_api: str) -> None:
    report = smoke.check_api(render_api, proxy_token="dashboard-secret", timeout=30)

    assert report.runtime == "recorded"
    assert "Microsoft" in report.fact_card_company
    with pytest.raises(smoke.SmokeFailure, match="401"):
        smoke.check_api(render_api, timeout=30)


def test_ci_deploy_hook_fallback_waits_for_every_other_job() -> None:
    workflow = yaml.safe_load(CI_YAML.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    deploy = jobs["deploy-api"]

    assert set(deploy["needs"]) == set(jobs) - {"deploy-api"}
    assert "refs/heads/master" in deploy["if"]
    assert "push" in deploy["if"]
    assert deploy["env"]["RENDER_DEPLOY_HOOK_URL"] == "${{ secrets.RENDER_DEPLOY_HOOK_URL }}"


def test_vercel_config_runs_the_ignored_build_step_on_fluid_compute_in_iad1() -> None:
    config = yaml.safe_load(VERCEL_JSON.read_text(encoding="utf-8"))  # JSON is YAML

    assert config["$schema"] == "https://openapi.vercel.sh/vercel.json"
    assert config["ignoreCommand"] == "sh scripts/ignore-build.sh"
    assert config["fluid"] is True
    assert config["regions"] == ["iad1"]


def test_proxy_route_runs_as_long_as_vercel_hobby_allows() -> None:
    match = re.search(
        r"^export const maxDuration = (\d+);$",
        PROXY_ROUTE.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )

    assert match is not None
    assert int(match.group(1)) == VERCEL_HOBBY_MAX_DURATION


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, path: str, text: str) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"change {path}")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def monorepo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    script = repo / "web" / "scripts" / "ignore-build.sh"
    script.parent.mkdir(parents=True)
    shutil.copy(IGNORE_BUILD, script)
    _commit(repo, "src/app.py", "print('api')\n")
    return repo


def _ignore_build(repo: Path, previous_sha: str | None) -> int:
    env = {key: value for key, value in os.environ.items() if not key.startswith("VERCEL_")}
    if previous_sha is not None:
        env["VERCEL_GIT_PREVIOUS_SHA"] = previous_sha
    # Vercel runs the command from the project's Root Directory, web/.
    result = subprocess.run(
        ["sh", "scripts/ignore-build.sh"], cwd=repo / "web", env=env, capture_output=True
    )
    return result.returncode


def test_ignored_build_skips_a_python_only_commit(monorepo: Path) -> None:
    deployed = _git(monorepo, "rev-parse", "HEAD")
    _commit(monorepo, "src/app.py", "print('api v2')\n")
    _commit(monorepo, "render.yaml", "services: []\n")

    assert _ignore_build(monorepo, deployed) == 0


def test_ignored_build_builds_when_web_changed_since_the_last_deploy(monorepo: Path) -> None:
    deployed = _git(monorepo, "rev-parse", "HEAD")
    _commit(monorepo, "web/app/page.tsx", "export default 1\n")
    _commit(monorepo, "src/app.py", "print('api v2')\n")

    assert _ignore_build(monorepo, deployed) == 1


def test_ignored_build_builds_without_a_previous_deploy(monorepo: Path) -> None:
    assert _ignore_build(monorepo, None) == 1
    assert _ignore_build(monorepo, "") == 1


def test_ignored_build_builds_when_the_previous_deploy_is_not_in_the_clone(
    monorepo: Path,
) -> None:
    assert _ignore_build(monorepo, "0" * 40) == 1
