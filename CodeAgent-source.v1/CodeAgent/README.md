# CodeAgent — DeepSeek V4-Pro Desktop Coding Agent

A simplified Claude-Code-style AI coding agent as a **Windows desktop
application**. It reads architecture documentation + PlantUML views,
preprocesses them to structured JSON, and autonomously generates a complete
project (the **Space Fractions desktop game**) through the **official DeepSeek
API (`deepseek-v4-pro`)** under a strict **$0.80 cost budget**.

> Model policy: **only** `https://api.deepseek.com` + `deepseek-v4-pro`.
> No Qwen / OpenAI / Gemini / Claude / `deepseek-chat` / fallback. The app
> never silently switches model or provider.

## Deliverables in this folder
- `dist/CodeAgent.exe` — standalone, double-click, **no Python required** on the target machine.
- `codeagent/` — full source (modular).
- `tests/` — 84 tests (unit / integration / API / sandbox / preprocessing / agent / cost / GUI smoke).
- `requirements.txt`, `requirements-dev.txt` — dependency manifests.
- `CodeAgent.spec`, `build_windows.bat`, `.github/workflows/build-windows.yml` — reproducible Windows build.
- `research_notes.md` — studied mechanisms + source-tree mapping.
- `docs/` — usage/cost report format, YouTube plan, acceptance checklist.
- The generated game lives in the sibling `SpaceFractionsGame/` folder (with its own exe).

## Architecture (modular)
| Module | Responsibility |
| --- | --- |
| `codeagent/agent.py` | Agent controller / loop, finish-validation gate, reports |
| `codeagent/llm.py` | DeepSeek V4-Pro client (tool calls, thinking toggle, retries, connection test) |
| `codeagent/tools.py` | Tool registry + workspace sandbox + restricted `run_command` |
| `codeagent/preprocess.py` | Markdown → structured JSON |
| `codeagent/uml.py` | UML element extraction (actors/classes/states/… ) |
| `codeagent/context.py` | Context compaction (old source args → summaries) |
| `codeagent/cost.py` | Budget guard (pre + post request), peak pricing |
| `codeagent/traceability.py` | Requirement → diagram → file → test report |
| `codeagent/validation.py` | Generated-project validation |
| `codeagent/config.py` | Settings (fixed DeepSeek identity, budget, pricing) |
| `codeagent/secrets_store.py` | DPAPI-encrypted API-key storage |
| `codeagent/gui.py` | Professional Tkinter desktop GUI |
| `codeagent/cli.py` | CLI: `gui` / `run` / `preprocess` / `test-connection` |

## Quick start (GUI)
1. Double-click `CodeAgent.exe` (or `python main.py`).
2. Enter your DeepSeek API key → **Test Connection** → **Save Key**
   (stored encrypted via Windows DPAPI; never logged).
3. Select `Architecture_Documentation.md`, `Architecture_View.md`, and an output directory.
4. **Start Task**. Watch the live log, progress, token usage, cost and budget remaining.
5. On completion, **Open Output Folder** to see the generated project + reports.

## Quick start (CLI)
```powershell
python main.py run --doc Architecture_Documentation.md --view Architecture_View.md --out generated
python main.py preprocess --doc ... --view ... -o pre.json
python main.py test-connection
```
Key via secure store, `CODEAGENT_API_KEY` env, or `--api-key`. Budget via `--budget` (default 0.80).

## Cost control (how spending stays under $1)
- Default budget **$0.80**; conservative **peak** pricing: cached input $0.044,
  uncached input $1.32, output $3.96 per 1M tokens (configurable in settings).
- **Post-request:** reads actual `prompt_cache_hit_tokens` /
  `prompt_cache_miss_tokens` / `completion_tokens`; treats all input as
  uncached when cache info is missing; accumulates cost after every response.
- **Pre-request:** estimates the next request, dynamically caps `max_tokens`
  to the affordable output budget, and **refuses** the request if the input
  alone cannot be afforded (with a safety margin).
- Files written before a budget stop are **preserved**; a `usage_report.json`
  is always saved. See `docs/usage_report_format.md`.

## Build the executable (reproducible)
```powershell
build_windows.bat
```
or manually:
```powershell
pip install -r requirements-dev.txt
python -m pytest tests -q
python -m PyInstaller CodeAgent.spec --noconfirm
```
CI: `.github/workflows/build-windows.yml` builds + tests on `windows-latest`.

## Tests
```powershell
python -m pytest tests -q
```
All API tests use **mocked** responses — no API money is spent by the test
suite. A live integration test runs only with an explicitly supplied key
(`test-connection` / a real `run`) within the budget.

## Security
- API key encrypted with Windows DPAPI (current-user bound); never in logs,
  config JSON, or source control.
- All file tools confined to the output workspace; `run_command` is
  allowlisted, shell-free, timeout-bounded, and gated for generated programs.

## License
MIT (see `LICENSE`).
