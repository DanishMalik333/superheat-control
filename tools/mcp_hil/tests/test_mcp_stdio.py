"""Real MCP round trip: start server.py over stdio with the SDK client, list the
tools, call hil_status and hil_run_tests (simulator), and check a dangerous tool
is refused.

The server is started from a copy of the repo layout it needs (tests/hil,
tools/plot_from_log.py, tools/mcp_hil/server.py) in a temp folder, so the run
doesn't overwrite the repo's own tests/hil/out.
"""
import json
import shutil
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import server

EXPECTED_TOOLS = {
    "hil_status", "hil_run_tests", "hil_get_last_results", "hil_explain_failure", "hil_plot",
    "hil_set_setpoint", "hil_ci_status", "hil_flash", "hil_reset", "hil_inject_link_fault",
}


def _fake_repo(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(server.REPO / "tests" / "hil", repo / "tests" / "hil",
                    ignore=shutil.ignore_patterns("out", "__pycache__"))
    (repo / "tools" / "mcp_hil").mkdir(parents=True)
    shutil.copy2(server.REPO / "tools" / "plot_from_log.py", repo / "tools" / "plot_from_log.py")
    shutil.copy2(server.REPO / "tools" / "mcp_hil" / "server.py", repo / "tools" / "mcp_hil" / "server.py")
    return repo


def _payload(result):
    assert not result.isError, result
    if result.structuredContent is not None:
        sc = result.structuredContent
        return sc.get("result", sc) if set(sc) == {"result"} else sc
    return json.loads(result.content[0].text)


async def _session(repo):
    params = StdioServerParameters(command=sys.executable,
                                   args=[str(repo / "tools" / "mcp_hil" / "server.py")],
                                   # merged by the SDK with its safe default environment
                                   env={"HIL_BACKEND": "sim"},
                                   cwd=str(repo))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            status = _payload(await session.call_tool("hil_status", {}))
            run = _payload(await session.call_tool("hil_run_tests", {"test": "step"}))
            bad = _payload(await session.call_tool("hil_run_tests", {"test": "step; rm -rf /"}))
            flash = _payload(await session.call_tool("hil_flash", {"confirm": True}))
            return {t.name for t in tools.tools}, status, run, bad, flash


def test_stdio_round_trip(tmp_path):
    repo = _fake_repo(tmp_path)
    names, status, run, bad, flash = anyio.run(_session, repo)

    assert names == EXPECTED_TOOLS
    assert status["ok"] is True and status["backend"] == "sim"
    assert status["dangerous_tools_enabled"] is False
    assert status["repo"] == str(repo)

    assert run["ok"] is True and run["exit_code"] == 0, run
    assert run["counts"]["passed"] == 1
    assert run["tests"][0]["test"] == "test_step_response"
    assert run["tests"][0]["metrics"]["overshoot_pct"] < 10
    assert (repo / "tests" / "hil" / "out" / "test_step_response.csv").exists()

    assert bad["ok"] is False and "unknown test" in bad["error"]
    assert flash["ok"] is False and flash["refused"] is True
