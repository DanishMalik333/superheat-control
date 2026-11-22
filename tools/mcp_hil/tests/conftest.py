"""Fixtures for the MCP server tests.

The server's tools write into tests/hil/out. So these tests never touch the
repo's own results, each run works on a copy of tests/hil in a temp folder and
points the server at it.
"""
import shutil
import sys
from pathlib import Path

import pytest

MCP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MCP_DIR))

import server  # noqa: E402

ENV_VARS = ("HIL_BACKEND", "HIL_ALLOW_DANGEROUS", "HIL_PORT", "HIL_MUTE_GPIO", "HIL_TIMEOUT_S")


def copy_hil(dest: Path) -> Path:
    hil = dest / "hil"
    shutil.copytree(server.REPO / "tests" / "hil", hil,
                    ignore=shutil.ignore_patterns("out", "__pycache__"))
    return hil


def _point_at(mp, hil: Path):
    mp.setattr(server, "HIL_DIR", hil)
    mp.setattr(server, "OUT_DIR", hil / "out")
    for v in ENV_VARS:
        mp.delenv(v, raising=False)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for v in ENV_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(server, "LAST_RUN", None)


@pytest.fixture
def bench(tmp_path, monkeypatch):
    """Server pointed at a fresh, empty copy of tests/hil."""
    hil = copy_hil(tmp_path)
    _point_at(monkeypatch, hil)
    return hil


def _session_run(tmp_path_factory, name, **kw):
    hil = copy_hil(tmp_path_factory.mktemp(name))
    with pytest.MonkeyPatch.context() as mp:
        _point_at(mp, hil)
        result = server.run_tests(**kw)
    return hil, result


@pytest.fixture(scope="session")
def shipped_run(tmp_path_factory):
    """The whole suite on the simulator with the shipped gains, run once."""
    return _session_run(tmp_path_factory, "shipped")


@pytest.fixture(scope="session")
def broken_run(tmp_path_factory):
    """The whole suite on the simulator with --sim-kp 0.3, run once."""
    return _session_run(tmp_path_factory, "broken", sim_kp=0.3)


@pytest.fixture
def results_of(monkeypatch):
    """Point the server at the out dir of a session run."""
    def use(run):
        hil, _ = run
        _point_at(monkeypatch, hil)
        return hil
    return use
