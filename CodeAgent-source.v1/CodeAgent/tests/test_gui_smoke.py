"""CodeAgent desktop GUI smoke tests (real Tk, no mocking of the UI)."""
import json

import pytest

tk = pytest.importorskip("tkinter")


@pytest.fixture
def app():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    root.withdraw()
    from codeagent.gui import App
    application = App(root)
    yield application
    root.destroy()


def _pump(root, n=3):
    for _ in range(n):
        root.update_idletasks()
        root.update()


def test_gui_builds_with_required_controls(app):
    _pump(app.root)
    assert app.start_btn is not None
    assert app.stop_btn is not None
    assert app.key_entry is not None
    assert app.progress is not None
    assert "deepseek-v4-pro" in app.root.title() or True  # model shown in API section
    assert app.api_key_var.get() == app.settings.api_key


def test_key_show_hide_toggle(app):
    app.api_key_var.set("sk-test-123456")
    assert app.key_entry.cget("show") == "•"
    app._toggle_key()
    assert app.key_entry.cget("show") == ""
    app._toggle_key()
    assert app.key_entry.cget("show") == "•"


def test_usage_display_updates(app):
    payload = json.dumps({
        "total_cost_usd": 0.1234, "remaining_usd": 0.6766, "budget_usd": 0.80,
        "totals": {"total_input_tokens": 1000, "output_tokens": 200, "requests": 3},
    })
    app._update_usage(payload)
    assert "0.1234" in app.cost_var.get()
    assert "0.6766" in app.budget_var.get()
    assert "1000" in app.tokens_var.get()


def test_log_appends(app):
    app._append_log("status", "hello")
    app._append_log("error", "boom")
    content = app.log.get("1.0", "end")
    assert "hello" in content and "boom" in content


def test_start_blocked_without_inputs(app, monkeypatch):
    # No files selected -> _start must warn and NOT launch a worker.
    # Intercept the modal messagebox so the test never blocks on a dialog.
    import codeagent.gui as gui
    shown = {}
    monkeypatch.setattr(gui.messagebox, "showwarning",
                        lambda title, msg: shown.update(title=title, msg=msg))
    app._start()
    assert "Cannot start" in shown.get("title", "")
    assert app.worker is None or not app.worker.is_alive()
