"""Professional Tkinter GUI for CodeAgent (DeepSeek V4-Pro).

Contains every control required by the assignment: title/version, API key
with show/hide, connection test, fixed model display, file selectors,
Start/Stop/Open-output, live log, progress indicator, token usage, cost and
budget-remaining displays, and final status. The API key is stored via
DPAPI and never appears in logs.
"""
from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, __version__
from .agent import Agent
from .config import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, Settings, load_settings, save_settings
from .cost import CostManager
from .llm import DeepSeekClient, LLMError
from .secrets_store import storage_description
from .tools import ToolRegistry, Workspace

EVENT_QUEUE: queue.Queue = queue.Queue()

# Palette
BG = "#f4f6fb"
CARD = "#ffffff"
ACCENT = "#2b59c3"
OK = "#1e7d32"
ERR = "#b3261e"
MUTED = "#5f6b7a"


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(f"{APP_NAME} {__version__} — DeepSeek V4-Pro Coding Agent")
        root.geometry("980x760")
        root.minsize(860, 640)
        root.configure(bg=BG)

        self.settings = load_settings()
        self.worker: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self._key_visible = False

        self._setup_style()
        self._build_ui()
        self._load_settings_into_ui()
        self._poll_events()

    # ------------------------------------------------------------------
    def _setup_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=BG, font=("Segoe UI", 10))
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD, relief="solid", borderwidth=1)
        style.configure("TLabel", background=BG, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=CARD)
        style.configure("Header.TLabel", background=ACCENT, foreground="white",
                        font=("Segoe UI Semibold", 14))
        style.configure("Sub.TLabel", background=ACCENT, foreground="#dbe4ff",
                        font=("Segoe UI", 9))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("CardMuted.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("TLabelframe", background=CARD, font=("Segoe UI Semibold", 10))
        style.configure("TLabelframe.Label", background=BG, foreground=ACCENT,
                        font=("Segoe UI Semibold", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=6)
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 10), padding=7)
        style.configure("OK.TLabel", background=BG, foreground=OK, font=("Segoe UI Semibold", 10))
        style.configure("ERR.TLabel", background=BG, foreground=ERR, font=("Segoe UI Semibold", 10))
        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#dde3ee")

    def _build_ui(self) -> None:
        # Header banner
        header = tk.Frame(self.root, bg=ACCENT)
        header.pack(fill="x")
        tk.Label(header, text=f"  {APP_NAME}  ·  v{__version__}", bg=ACCENT, fg="white",
                 font=("Segoe UI Semibold", 15), anchor="w").pack(side="left", pady=8)
        tk.Label(header, text="Architecture → Project  ·  DeepSeek V4-Pro  ", bg=ACCENT,
                 fg="#dbe4ff", font=("Segoe UI", 10)).pack(side="right", pady=8)

        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, padx=12, pady=8)

        self._build_api_section(body)
        self._build_files_section(body)
        self._build_run_section(body)
        self._build_metrics_section(body)
        self._build_log_section(body)

    # --- API ----------------------------------------------------------
    def _build_api_section(self, parent) -> None:
        box = ttk.Labelframe(parent, text=" DeepSeek API ", padding=10)
        box.pack(fill="x", pady=(0, 8))

        row0 = ttk.Frame(box)
        row0.pack(fill="x")
        ttk.Label(row0, text="Model:", style="Card.TLabel").pack(side="left")
        ttk.Label(row0, text=f" {DEEPSEEK_MODEL} ", style="Card.TLabel",
                  font=("Consolas", 10, "bold"), foreground=ACCENT).pack(side="left")
        ttk.Label(row0, text=f"   Endpoint: {DEEPSEEK_BASE_URL}", style="CardMuted.TLabel").pack(side="left")
        ttk.Label(row0, text="(fixed — no other model/provider is used)", style="CardMuted.TLabel").pack(side="left", padx=6)

        row1 = ttk.Frame(box)
        row1.pack(fill="x", pady=(6, 0))
        ttk.Label(row1, text="API Key:", style="Card.TLabel").pack(side="left")
        self.api_key_var = tk.StringVar()
        self.key_entry = ttk.Entry(row1, textvariable=self.api_key_var, show="•", width=52)
        self.key_entry.pack(side="left", padx=6)
        self.show_btn = ttk.Button(row1, text="Show", width=6, command=self._toggle_key)
        self.show_btn.pack(side="left")
        ttk.Button(row1, text="Test Connection", command=self._test_connection).pack(side="left", padx=6)
        ttk.Button(row1, text="Save Key", command=self._save_settings).pack(side="left")
        self.conn_var = tk.StringVar(value="")
        ttk.Label(row1, textvariable=self.conn_var, style="CardMuted.TLabel").pack(side="left", padx=8)

        ttk.Label(box, text=f"Key storage: {storage_description()}. The key is never written to logs or source control.",
                  style="CardMuted.TLabel").pack(anchor="w", pady=(6, 0))

    # --- Files --------------------------------------------------------
    def _build_files_section(self, parent) -> None:
        box = ttk.Labelframe(parent, text=" Task Inputs & Output ", padding=10)
        box.pack(fill="x", pady=(0, 8))
        self.doc_var = tk.StringVar()
        self.view_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self._file_row(box, "Architecture documentation (.md):", self.doc_var, self._pick_doc)
        self._file_row(box, "Architecture views (.md):", self.view_var, self._pick_view)
        self._file_row(box, "Output directory:", self.out_var, self._pick_out)

    def _file_row(self, parent, label, var, command) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label, style="Card.TLabel", width=32).pack(side="left")
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="Browse…", command=command).pack(side="left")

    # --- Run ----------------------------------------------------------
    def _build_run_section(self, parent) -> None:
        box = ttk.Labelframe(parent, text=" Run ", padding=10)
        box.pack(fill="x", pady=(0, 8))

        instr = ttk.Frame(box)
        instr.pack(fill="x")
        ttk.Label(instr, text="Extra instruction (optional):", style="Card.TLabel").pack(side="left")
        self.extra_text = tk.Text(instr, height=2, font=("Segoe UI", 9))
        self.extra_text.pack(side="left", fill="x", expand=True, padx=6)

        ctrl = ttk.Frame(box)
        ctrl.pack(fill="x", pady=(6, 0))
        self.start_btn = ttk.Button(ctrl, text="▶  Start Task", style="Accent.TButton", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(ctrl, text="■  Stop Task", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        ttk.Button(ctrl, text="Open Output Folder", command=self._open_output).pack(side="left", padx=6)
        self.allow_generated_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Permit running generated programs",
                        variable=self.allow_generated_var).pack(side="left", padx=10)

        prog = ttk.Frame(box)
        prog.pack(fill="x", pady=(6, 0))
        self.progress = ttk.Progressbar(prog, mode="determinate", maximum=60)
        self.progress.pack(side="left", fill="x", expand=True)
        self.status_var = tk.StringVar(value="Idle.")
        ttk.Label(prog, textvariable=self.status_var, style="Muted.TLabel", width=46).pack(side="left", padx=8)

    # --- Metrics ------------------------------------------------------
    def _build_metrics_section(self, parent) -> None:
        box = ttk.Labelframe(parent, text=" Token Usage & Cost ", padding=10)
        box.pack(fill="x", pady=(0, 8))
        grid = ttk.Frame(box)
        grid.pack(fill="x")
        self.tokens_var = tk.StringVar(value="Input: 0  |  Output: 0  |  Requests: 0")
        self.cost_var = tk.StringVar(value="Estimated cost: $0.0000")
        self.budget_var = tk.StringVar(value=f"Budget remaining: ${self.settings.budget_usd:.2f}")
        for i, (var, style) in enumerate([(self.tokens_var, "Card.TLabel"),
                                          (self.cost_var, "Card.TLabel"),
                                          (self.budget_var, "OK.TLabel")]):
            lbl = ttk.Label(grid, textvariable=var, style=style)
            lbl.grid(row=0, column=i, sticky="w", padx=(0, 24))
        self.final_var = tk.StringVar(value="Final status: —")
        ttk.Label(box, textvariable=self.final_var, style="CardMuted.TLabel").pack(anchor="w", pady=(4, 0))

    # --- Log ----------------------------------------------------------
    def _build_log_section(self, parent) -> None:
        box = ttk.Labelframe(parent, text=" Agent Activity Log ", padding=6)
        box.pack(fill="both", expand=True)
        self.log = tk.Text(box, state="disabled", wrap="word", font=("Consolas", 9),
                           bg="#10141c", fg="#d6deeb", insertbackground="white")
        scroll = ttk.Scrollbar(box, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for tag, color in [("status", "#82aaff"), ("tool", "#c3e88d"), ("tool_result", "#89ddff"),
                           ("assistant", "#ffcb6b"), ("error", "#ff5370"), ("usage", "#f78c6c")]:
            self.log.tag_configure(tag, foreground=color)

    # ------------------------------------------------------------------
    def _load_settings_into_ui(self) -> None:
        self.api_key_var.set(self.settings.api_key)
        self.budget_var.set(f"Budget remaining: ${self.settings.budget_usd:.2f}")

    def _toggle_key(self) -> None:
        self._key_visible = not self._key_visible
        self.key_entry.configure(show="" if self._key_visible else "•")
        self.show_btn.configure(text="Hide" if self._key_visible else "Show")

    def _collect_settings(self) -> Settings:
        s = Settings(
            api_key=self.api_key_var.get().strip(),
            temperature=self.settings.temperature,
            max_iterations=self.settings.max_iterations,
            request_timeout=self.settings.request_timeout,
            budget_usd=self.settings.budget_usd,
            thinking_enabled=self.settings.thinking_enabled,
            pricing=self.settings.pricing,
        )
        return s

    def _save_settings(self) -> None:
        s = self._collect_settings()
        if not s.api_key:
            messagebox.showwarning("Invalid settings", "API key is empty.")
            return
        save_settings(s)
        self.settings = s
        self._append_log("status", f"Settings saved. Key storage: {storage_description()}.")

    def _test_connection(self) -> None:
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showwarning("Test Connection", "Enter an API key first.")
            return
        self.conn_var.set("Testing…")
        self._append_log("status", "Testing DeepSeek API connection (tiny request)…")

        def work():
            try:
                client = DeepSeekClient(key, timeout=60)
                info = client.test_connection()
                EVENT_QUEUE.put(("conn", True, f"OK · {info['model']} · reply={info['reply']!r}"))
            except LLMError as e:
                EVENT_QUEUE.put(("conn", False, str(e)))

        threading.Thread(target=work, daemon=True).start()

    # --- pickers ------------------------------------------------------
    def _pick_doc(self) -> None:
        p = filedialog.askopenfilename(title="Select architecture documentation",
                                       filetypes=[("Markdown", "*.md"), ("All files", "*.*")])
        if p:
            self.doc_var.set(p)

    def _pick_view(self) -> None:
        p = filedialog.askopenfilename(title="Select architecture views",
                                       filetypes=[("Markdown", "*.md"), ("All files", "*.*")])
        if p:
            self.view_var.set(p)

    def _pick_out(self) -> None:
        p = filedialog.askdirectory(title="Select output directory")
        if p:
            self.out_var.set(p)

    def _open_output(self) -> None:
        out = self.out_var.get().strip()
        if out and Path(out).is_dir():
            import os
            os.startfile(out)
        else:
            messagebox.showinfo("Output folder", "Output directory does not exist yet.")

    # --- run ----------------------------------------------------------
    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        s = self._collect_settings()
        problems = s.validate()
        doc, view, out = self.doc_var.get().strip(), self.view_var.get().strip(), self.out_var.get().strip()
        if not doc or not Path(doc).is_file():
            problems.append("Architecture documentation file not found.")
        if not view or not Path(view).is_file():
            problems.append("Architecture views file not found.")
        if not out:
            problems.append("Output directory is not set.")
        if problems:
            messagebox.showwarning("Cannot start", "\n".join(problems))
            return

        save_settings(s)
        self.settings = s
        self.cancel_event = threading.Event()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.configure(value=0, maximum=s.max_iterations)
        self.final_var.set("Final status: running…")
        self._append_log("status", f"Starting task. Output: {out}")

        extra = self.extra_text.get("1.0", "end").strip()
        allow_gen = self.allow_generated_var.get()
        self.worker = threading.Thread(target=self._run_agent,
                                       args=(s, doc, view, out, extra, allow_gen), daemon=True)
        self.worker.start()

    def _run_agent(self, s, doc, view, out, extra, allow_gen) -> None:
        try:
            client = DeepSeekClient(s.api_key, timeout=s.request_timeout,
                                    temperature=s.temperature, thinking_enabled=s.thinking_enabled)
            registry = ToolRegistry(Workspace(out))
            registry.generated_permission = allow_gen
            cost = CostManager(budget_usd=s.budget_usd, pricing=s.pricing)
            agent = Agent(client, registry, cost_manager=cost, max_iterations=s.max_iterations,
                          on_event=lambda kind, text: EVENT_QUEUE.put((kind, text)),
                          cancel_event=self.cancel_event)
            result = agent.run(doc, view, extra)
            EVENT_QUEUE.put(("done", result.status, result.summary))
        except Exception as e:
            EVENT_QUEUE.put(("done", "error", str(e)))

    def _stop(self) -> None:
        self.cancel_event.set()
        self._append_log("status", "Stop requested; halting after the current step (files preserved).")

    # --- events -------------------------------------------------------
    def _poll_events(self) -> None:
        try:
            while True:
                item = EVENT_QUEUE.get_nowait()
                kind = item[0]
                if kind == "done":
                    _, status, summary = item
                    self.start_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self.final_var.set(f"Final status: {status.upper()}")
                    self.status_var.set(f"Finished: {status}")
                    self._append_log("status", f"=== Finished: {status} === {summary}")
                    if status == "completed":
                        messagebox.showinfo("Task finished", f"Project generated.\n\n{summary}")
                    elif status in ("error", "budget_exceeded"):
                        messagebox.showwarning("Task ended", summary)
                elif kind == "conn":
                    _, ok, msg = item
                    self.conn_var.set(("✓ " if ok else "✗ ") + msg[:60])
                    self._append_log("status" if ok else "error", f"Connection test: {msg}")
                elif kind == "usage":
                    self._update_usage(item[1])
                else:
                    self._append_log(kind, item[1])
                    if kind == "status":
                        self.status_var.set(item[1][:80])
                        if item[1].startswith("Iteration "):
                            try:
                                n = int(item[1].split()[1].split("/")[0])
                                self.progress.configure(value=n)
                            except (ValueError, IndexError):
                                pass
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _update_usage(self, payload_json: str) -> None:
        try:
            u = json.loads(payload_json)
        except ValueError:
            return
        t = u.get("totals", {})
        self.tokens_var.set(f"Input: {t.get('total_input_tokens', 0)}  |  Output: {t.get('output_tokens', 0)}  |  Requests: {t.get('requests', 0)}")
        self.cost_var.set(f"Estimated cost: ${u.get('total_cost_usd', 0):.4f}")
        remaining = u.get("remaining_usd", 0)
        self.budget_var.set(f"Budget remaining: ${remaining:.4f}")

    def _append_log(self, kind: str, text: str) -> None:
        self.log.configure(state="normal")
        prefix = {"status": "[*] ", "tool": "[tool] ", "tool_result": "    → ",
                  "assistant": "[model] ", "error": "[!] ", "usage": "[cost] "}.get(kind, "")
        self.log.insert("end", prefix + text + "\n", kind)
        self.log.see("end")
        self.log.configure(state="disabled")


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
