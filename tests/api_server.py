"""An in-process API server and the image smoke script, shared by HTTP-level tests."""

from __future__ import annotations

import importlib.util
import socket
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import uvicorn
from fastapi import FastAPI

_SMOKE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke_api_image.py"


def _load_smoke() -> ModuleType:
    spec = importlib.util.spec_from_file_location("smoke_api_image", _SMOKE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


# scripts/smoke_api_image.py, loaded by path (scripts/ is not a package).
smoke = _load_smoke()


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def serve(app: FastAPI) -> Iterator[str]:
    """Run ``app`` on a free local port for the life of a fixture; yield its base URL."""
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    runner = threading.Thread(target=server.run, daemon=True)
    runner.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        runner.join(timeout=10)
