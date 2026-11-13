import pytest

from codeagent.tools import MAX_WRITE_BYTES, ToolRegistry, Workspace


@pytest.fixture
def registry(tmp_path):
    return ToolRegistry(Workspace(tmp_path / "out"))


def test_write_read_roundtrip(registry, tmp_path):
    assert registry.execute("write_file", {"path": "src/app.py", "content": "print('hi')\n"}).startswith("OK:")
    assert (tmp_path / "out" / "src" / "app.py").read_text() == "print('hi')\n"
    assert registry.execute("read_file", {"path": "src/app.py"}) == "print('hi')\n"


@pytest.mark.parametrize("bad", ["../escape.txt", "..\\..\\e.txt", "/etc/passwd", "C:/Windows/e.txt"])
def test_sandbox_blocks_escapes(registry, bad, tmp_path):
    assert registry.execute("write_file", {"path": bad, "content": "x"}).startswith("ERROR:")
    assert not (tmp_path / "escape.txt").exists()


def test_sandbox_blocks_symlink_escape(registry, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = registry.ws.root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not permitted")
    assert registry.execute("write_file", {"path": "link/pwned.txt", "content": "x"}).startswith("ERROR:")
    assert not (outside / "pwned.txt").exists()


def test_search_files(registry):
    registry.execute("write_file", {"path": "a.py", "content": "def hello():\n    pass\n"})
    out = registry.execute("search_files", {"pattern": "hello"})
    assert "a.py:1" in out


def test_search_invalid_regex(registry):
    assert registry.execute("search_files", {"pattern": "("}).startswith("ERROR:")


def test_run_command_rejects_unapproved(registry):
    assert registry.execute("run_command", {"command": "curl http://x"}).startswith("ERROR:")
    assert registry.execute("run_command", {"command": "notepad.exe"}).startswith("ERROR:")


def test_run_command_rejects_destructive(registry):
    assert registry.execute("run_command", {"command": "python rm -rf /"}).startswith("ERROR:")


def test_run_command_generated_needs_permission(registry):
    registry.execute("write_file", {"path": "gen.py", "content": "print(1)\n"})
    # model flag true but user permission off
    assert registry.execute("run_command", {"command": "python gen.py", "allow_generated": True}).startswith("ERROR:")
    registry.generated_permission = True
    out = registry.execute("run_command", {"command": "python gen.py", "allow_generated": True})
    assert "exit_code=0" in out


def test_run_command_runs_pytest_module(registry):
    registry.execute("write_file", {"path": "test_ok.py", "content": "def test_ok():\n    assert True\n"})
    out = registry.execute("run_command", {"command": "python -m pytest test_ok.py -q"})
    assert "exit_code=0" in out


def test_run_command_timeout(registry, monkeypatch):
    import codeagent.tools as t
    monkeypatch.setattr(t, "COMMAND_TIMEOUT", 0)
    registry.execute("write_file", {"path": "slow.py", "content": "import time; time.sleep(5)\n"})
    registry.generated_permission = True
    out = registry.execute("run_command", {"command": "python slow.py", "allow_generated": True})
    assert "timed out" in out


def test_unknown_tool(registry):
    assert registry.execute("rm_rf", {}).startswith("ERROR:")


def test_bad_arguments(registry):
    assert registry.execute("write_file", {"path": "x"}).startswith("ERROR:")
    assert registry.execute("write_file", "nope").startswith("ERROR:")


def test_write_size_cap(registry):
    assert registry.execute("write_file", {"path": "b.txt", "content": "x" * (MAX_WRITE_BYTES + 1)}).startswith("ERROR:")


def test_finish(registry):
    assert registry.execute("finish", {"summary": "done"}).startswith("FINISH:")


def test_schemas_include_all_tools(registry):
    names = {s["function"]["name"] for s in registry.schemas()}
    assert {"write_file", "read_file", "list_files", "search_files", "run_command", "finish"} <= names
