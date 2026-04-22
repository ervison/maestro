# SDLC Gaps Web UI — Blocking Gap Questionnaire

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After the LLM generates 03-gaps.md, pause the pipeline, open a local web UI for the user to answer all `[GAP]` questions (each with selectable options + a recommended option), then continue generating artifacts 04–13 with those answers enriched into the context.

**Architecture:** A temporary `GapsServer` (stdlib `http.server`, same pattern as the existing dashboard) serves a single-page HTML form. The harness pauses after generating GAPS, blocks on `asyncio.Event` until the server sets it when the user submits answers, then enriches the `SDLCRequest.prompt` with the resolved answers before continuing artifact generation. The existing `maestro/dashboard/` is reused only for its server-startup pattern — the gaps UI gets its own file `maestro/sdlc/gaps_server.py` and `maestro/sdlc/static/gaps.html`.

**Tech Stack:** Python stdlib `http.server`, `threading`, `asyncio`, `json`; vanilla HTML/CSS/JS (no framework, matches dashboard style). No new pip dependencies.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `maestro/sdlc/gaps_server.py` | **Create** | `GapsServer` — serves `gaps.html`, parses `[GAP]` items from markdown, exposes `GET /gaps` (JSON), `POST /answers` (JSON), blocks until submission |
| `maestro/sdlc/static/gaps.html` | **Create** | Single-page questionnaire UI: dark/light theme, options per gap, recommended badge, submit button |
| `maestro/sdlc/harness.py` | **Modify** | After GAPS artifact, call `await resolve_gaps(artifact, port)` which starts GapsServer and blocks; inject answers into `effective_request.prompt` |
| `maestro/sdlc/schemas.py` | **Modify** | Add `GapItem(question, options, recommended_index)` and `GapAnswer(question, chosen_option)` dataclasses |
| `maestro/cli.py` | **Modify** | Print "Opening gap questionnaire at http://localhost:PORT — answer all questions and click Submit" |
| `tests/test_sdlc_gaps_server.py` | **Create** | Unit tests for gap parsing, server answer round-trip |
| `tests/test_sdlc_harness.py` | **Modify** | Add test: harness with mock server resolves gaps and enriches prompt |

---

## Task 1: Add GapItem/GapAnswer schemas

**Files:**
- Modify: `maestro/sdlc/schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sdlc_schemas.py  (append to existing file)
def test_gap_item_dataclass():
    from maestro.sdlc.schemas import GapItem
    item = GapItem(
        question="What is the target audience?",
        options=["B2C consumers", "B2B companies", "Internal teams"],
        recommended_index=0,
    )
    assert item.question == "What is the target audience?"
    assert item.options[0] == "B2C consumers"
    assert item.recommended_index == 0


def test_gap_answer_dataclass():
    from maestro.sdlc.schemas import GapAnswer
    ans = GapAnswer(question="What is the target audience?", chosen_option="B2C consumers")
    assert ans.chosen_option == "B2C consumers"
```

- [ ] **Step 2: Run to verify failure**

```
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
.venv/bin/pytest tests/test_sdlc_schemas.py::test_gap_item_dataclass tests/test_sdlc_schemas.py::test_gap_answer_dataclass -v
```
Expected: `ImportError` — `GapItem` not defined yet.

- [ ] **Step 3: Add dataclasses to schemas.py**

Append to `maestro/sdlc/schemas.py`:

```python
@dataclass
class GapItem:
    """A single gap question with answer options."""

    question: str
    options: list[str]
    recommended_index: int = 0


@dataclass
class GapAnswer:
    """User's answer to a single gap question."""

    question: str
    chosen_option: str
```

- [ ] **Step 4: Run to verify pass**

```
.venv/bin/pytest tests/test_sdlc_schemas.py::test_gap_item_dataclass tests/test_sdlc_schemas.py::test_gap_answer_dataclass -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add maestro/sdlc/schemas.py tests/test_sdlc_schemas.py
git commit -m "feat(sdlc): add GapItem and GapAnswer schema dataclasses"
```

---

## Task 2: Create gap parser (parse [GAP] items from generated markdown)

**Files:**
- Create: `maestro/sdlc/gaps_server.py` (first section — the parser function only)
- Create: `tests/test_sdlc_gaps_server.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_sdlc_gaps_server.py`:

```python
"""Tests for the gaps server — parser and server round-trip."""
from __future__ import annotations


GAP_MARKDOWN = """\
# Gaps

[GAP] What is the target audience? (B2C or B2B?)
[GAP] What is the expected monthly active user count?
[GAP] Is SSO required?
"""


def test_parse_gaps_returns_gap_items():
    from maestro.sdlc.gaps_server import parse_gaps
    items = parse_gaps(GAP_MARKDOWN)
    assert len(items) == 3
    assert items[0].question == "What is the target audience? (B2C or B2B?)"
    assert len(items[0].options) >= 2  # LLM-suggested options generated
    assert items[0].recommended_index == 0


def test_parse_gaps_empty_content():
    from maestro.sdlc.gaps_server import parse_gaps
    items = parse_gaps("# Gaps\n\nNo gaps found.\n")
    assert items == []


def test_parse_gaps_no_gap_tag():
    from maestro.sdlc.gaps_server import parse_gaps
    items = parse_gaps("# Gaps\n\nSome text without GAP markers.\n")
    assert items == []
```

- [ ] **Step 2: Run to verify failure**

```
.venv/bin/pytest tests/test_sdlc_gaps_server.py -v
```
Expected: `ModuleNotFoundError` — `gaps_server` not created yet.

- [ ] **Step 3: Create maestro/sdlc/gaps_server.py with parse_gaps**

Create `maestro/sdlc/gaps_server.py`:

```python
"""Gaps questionnaire server — blocks pipeline until user answers all [GAP] items."""
from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from maestro.sdlc.schemas import GapAnswer, GapItem

_STATIC_DIR = Path(__file__).parent / "static"

_DEFAULT_OPTIONS: list[str] = [
    "Yes",
    "No",
    "Not decided yet",
    "Other (specify in notes)",
]


def parse_gaps(gaps_markdown: str) -> list[GapItem]:
    """Extract [GAP] items from the generated 03-gaps.md content.

    Each [GAP] line becomes a GapItem. Options are generated heuristically:
    - Yes/No questions → ["Yes", "No", "Needs discussion"]
    - Questions with parenthesised options → split on ' or '
    - Default fallback → generic open-ended options
    """
    items: list[GapItem] = []
    for line in gaps_markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("[GAP]"):
            continue
        question = stripped[len("[GAP]"):].strip()
        if not question:
            continue
        options = _infer_options(question)
        items.append(GapItem(question=question, options=options, recommended_index=0))
    return items


def _infer_options(question: str) -> list[str]:
    """Heuristically derive answer options from question text."""
    q_lower = question.lower()

    # Parenthesised alternatives: "What is X? (A or B?)"
    paren_match = re.search(r"\(([^)]+)\)", question)
    if paren_match:
        inner = paren_match.group(1)
        parts = [p.strip().rstrip("?") for p in re.split(r"\s+or\s+", inner, flags=re.IGNORECASE)]
        if len(parts) >= 2:
            return parts + ["Needs discussion", "Not applicable"]

    # Binary yes/no
    yes_no_keywords = ("is ", "are ", "will ", "should ", "does ", "do ", "has ", "have ", "can ", "must ")
    if any(q_lower.startswith(kw) for kw in yes_no_keywords):
        return ["Yes", "No", "Needs discussion", "Not applicable"]

    # Quantity/scale questions
    if any(kw in q_lower for kw in ("how many", "how much", "count", "number", "volume", "scale")):
        return ["< 1,000 / month", "1,000–100,000 / month", "> 100,000 / month", "Unknown / TBD"]

    # Audience questions
    if any(kw in q_lower for kw in ("audience", "user", "customer", "persona", "target")):
        return ["B2C consumers", "B2B companies", "Internal teams", "Mixed / TBD"]

    # Fallback
    return ["Option A (define in notes)", "Option B (define in notes)", "Needs discussion", "Not applicable"]
```

- [ ] **Step 4: Run to verify pass**

```
.venv/bin/pytest tests/test_sdlc_gaps_server.py::test_parse_gaps_returns_gap_items tests/test_sdlc_gaps_server.py::test_parse_gaps_empty_content tests/test_sdlc_gaps_server.py::test_parse_gaps_no_gap_tag -v
```
Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add maestro/sdlc/gaps_server.py tests/test_sdlc_gaps_server.py
git commit -m "feat(sdlc): add gap parser that extracts [GAP] items with inferred options"
```

---

## Task 3: Create the GapsServer (HTTP server + blocking wait)

**Files:**
- Modify: `maestro/sdlc/gaps_server.py` (append server class + `serve_gaps` function)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_sdlc_gaps_server.py`:

```python
import threading
import time
import urllib.request
import urllib.error


def test_gaps_server_serves_answers_endpoint():
    """GapsServer serves GET /gaps and accepts POST /answers."""
    from maestro.sdlc.gaps_server import GapsServer, parse_gaps

    items = parse_gaps("[GAP] Is SSO required?\n[GAP] What is the scale?\n")
    assert len(items) == 2

    server = GapsServer(items, port=0)  # port=0 = OS assigns free port
    server.start()
    port = server.port
    try:
        # GET /gaps returns JSON list
        resp = urllib.request.urlopen(f"http://localhost:{port}/gaps", timeout=3)
        data = json.loads(resp.read())
        assert len(data) == 2
        assert data[0]["question"] == "Is SSO required?"
        assert "options" in data[0]
        assert "recommended_index" in data[0]

        # POST /answers resolves the server
        answers = [
            {"question": "Is SSO required?", "chosen_option": "Yes"},
            {"question": "What is the scale?", "chosen_option": "Unknown / TBD"},
        ]
        req = urllib.request.Request(
            f"http://localhost:{port}/answers",
            data=json.dumps(answers).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)

        # Wait for server to record answers
        time.sleep(0.1)
        result = server.get_answers(timeout=1.0)
        assert len(result) == 2
        assert result[0].chosen_option == "Yes"
    finally:
        server.stop()


def test_gaps_server_get_answers_blocks_until_submission():
    """get_answers() blocks and only returns after POST /answers."""
    from maestro.sdlc.gaps_server import GapsServer, parse_gaps

    items = parse_gaps("[GAP] Any gaps?\n")
    server = GapsServer(items, port=0)
    server.start()
    port = server.port

    answers_received: list = []

    def submit_later():
        time.sleep(0.1)
        answers = [{"question": "Any gaps?", "chosen_option": "Yes"}]
        req = urllib.request.Request(
            f"http://localhost:{port}/answers",
            data=json.dumps(answers).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)

    t = threading.Thread(target=submit_later)
    t.start()
    result = server.get_answers(timeout=2.0)
    t.join()
    server.stop()

    assert result is not None
    assert len(result) == 1
    assert result[0].question == "Any gaps?"
```

- [ ] **Step 2: Run to verify failure**

```
.venv/bin/pytest tests/test_sdlc_gaps_server.py::test_gaps_server_serves_answers_endpoint tests/test_sdlc_gaps_server.py::test_gaps_server_get_answers_blocks_until_submission -v
```
Expected: FAIL — `GapsServer` not defined yet.

- [ ] **Step 3: Append GapsServer to gaps_server.py**

Append to `maestro/sdlc/gaps_server.py` (after the existing `_infer_options` function):

```python

class GapsServer:
    """HTTP server that presents gap questions and blocks until user answers."""

    def __init__(self, items: list[GapItem], port: int = 4041) -> None:
        self._items = items
        self._requested_port = port
        self._answers: list[GapAnswer] | None = None
        self._event = threading.Event()
        self._server: ThreadingHTTPServer | None = None

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("Server not started")
        return self._server.server_address[1]

    def start(self) -> None:
        """Start the HTTP server in a daemon thread."""
        ThreadingHTTPServer.allow_reuse_address = True
        self._server = ThreadingHTTPServer(
            ("127.0.0.1", self._requested_port),
            self._make_handler(),
        )
        t = threading.Thread(target=self._server.serve_forever, daemon=True)
        t.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None

    def get_answers(self, timeout: float | None = None) -> list[GapAnswer] | None:
        """Block until user submits answers, then return them."""
        self._event.wait(timeout=timeout)
        return self._answers

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        server_ref = self

        class GapsHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                pass

            def do_GET(self) -> None:
                if self.path in ("/", ""):
                    self._serve_html()
                elif self.path == "/gaps":
                    self._serve_gaps_json()
                else:
                    self.send_error(404)

            def do_POST(self) -> None:
                if self.path == "/answers":
                    self._receive_answers()
                else:
                    self.send_error(404)

            def _serve_html(self) -> None:
                html_path = _STATIC_DIR / "gaps.html"
                try:
                    content = html_path.read_bytes()
                except FileNotFoundError:
                    self.send_error(404, "gaps.html not found")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def _serve_gaps_json(self) -> None:
                payload = [
                    {
                        "question": item.question,
                        "options": item.options,
                        "recommended_index": item.recommended_index,
                    }
                    for item in server_ref._items
                ]
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def _receive_answers(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                try:
                    data: list[dict[str, str]] = json.loads(raw)
                    answers = [
                        GapAnswer(
                            question=item["question"],
                            chosen_option=item["chosen_option"],
                        )
                        for item in data
                    ]
                except (json.JSONDecodeError, KeyError, TypeError):
                    self.send_error(400, "Invalid JSON")
                    return

                server_ref._answers = answers
                server_ref._event.set()

                body = b'{"status": "ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return GapsHandler


def serve_gaps(items: list[GapItem], port: int = 4041) -> "GapsServer":
    """Start a GapsServer, return it (caller must call get_answers() to block)."""
    server = GapsServer(items, port=port)
    server.start()
    return server
```

- [ ] **Step 4: Run to verify pass**

```
.venv/bin/pytest tests/test_sdlc_gaps_server.py -v
```
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add maestro/sdlc/gaps_server.py tests/test_sdlc_gaps_server.py
git commit -m "feat(sdlc): add GapsServer HTTP server for gap questionnaire"
```

---

## Task 4: Create the gaps.html UI

**Files:**
- Create: `maestro/sdlc/static/gaps.html`

The UI must:
- Match the existing dark/light theme of the dashboard (same CSS variables)
- Fetch `/gaps` on load and render one card per gap
- Each card shows the question + radio buttons for each option
- Recommended option is visually highlighted with a "recommended" badge
- Submit button sends `POST /answers` with JSON, then shows a "Pipeline resuming…" message

- [ ] **Step 1: Create maestro/sdlc/static/ and gaps.html**

```bash
mkdir -p maestro/sdlc/static
```

Create `maestro/sdlc/static/gaps.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Maestro — Gap Questionnaire</title>
<style>
  :root {
    --bg:        #1a1d23;
    --surface:   #252932;
    --border:    #3d4452;
    --text:      #e2e8f0;
    --text-title:#f1f5f9;
    --text-muted:#94a3b8;
    --accent:    #60a5fa;
    --accent-bg: #1e2d4a;
    --green:     #4ade80;
    --green-bg:  #14532d;
    --yellow:    #fbbf24;
    --red:       #f87171;
  }
  :root.light {
    --bg:        #f1f5f9;
    --surface:   #ffffff;
    --border:    #cbd5e1;
    --text:      #1e293b;
    --text-title:#0f172a;
    --text-muted:#64748b;
    --accent:    #2563eb;
    --accent-bg: #dbeafe;
    --green:     #16a34a;
    --green-bg:  #dcfce7;
    --yellow:    #b45309;
    --red:       #dc2626;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 14px;
    min-height: 100vh;
    padding: 32px 16px;
  }
  .container { max-width: 760px; margin: 0 auto; }
  header {
    margin-bottom: 32px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
  }
  h1 { font-size: 20px; color: var(--text-title); }
  .subtitle { color: var(--text-muted); font-size: 12px; margin-top: 4px; }
  #theme-btn {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 5px 12px;
    color: var(--text-muted);
    font-family: inherit;
    font-size: 12px;
    cursor: pointer;
  }
  #theme-btn:hover { color: var(--text-title); border-color: var(--accent); }

  .gap-card {
    background: var(--surface);
    border: 1.5px solid var(--border);
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 16px;
  }
  .gap-number { font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px; }
  .gap-question { font-size: 15px; font-weight: 600; color: var(--text-title); margin-bottom: 16px; line-height: 1.5; }

  .options { display: flex; flex-direction: column; gap: 8px; }
  .option-label {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border: 1.5px solid var(--border);
    border-radius: 6px;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
  }
  .option-label:hover { border-color: var(--accent); }
  .option-label.recommended { border-color: var(--yellow); }
  .option-label input[type="radio"] { accent-color: var(--accent); width: 16px; height: 16px; flex-shrink: 0; }
  .option-label.selected { border-color: var(--accent); background: var(--accent-bg); }
  .option-text { flex: 1; }
  .rec-badge {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--yellow);
    border: 1px solid var(--yellow);
    border-radius: 10px;
    padding: 1px 7px;
    flex-shrink: 0;
  }

  footer { margin-top: 32px; display: flex; gap: 12px; align-items: center; }
  #submit-btn {
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: 10px 28px;
    font-family: inherit;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  #submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  #submit-btn:hover:not(:disabled) { opacity: 0.85; }
  #status { font-size: 13px; color: var(--text-muted); }
  #status.ok { color: var(--green); }
  #status.err { color: var(--red); }

  #loading, #done-msg { text-align: center; color: var(--text-muted); padding: 48px; display: none; }
</style>
</head>
<body>
<div class="container">
  <header>
    <div>
      <h1>Gap Questionnaire</h1>
      <div class="subtitle">Answer all questions to continue the SDLC pipeline</div>
    </div>
    <button id="theme-btn" onclick="toggleTheme()">☀️ Light</button>
  </header>

  <div id="loading">Loading questions…</div>
  <div id="questions"></div>
  <div id="done-msg">✓ Answers submitted — pipeline is resuming. You can close this tab.</div>

  <footer>
    <button id="submit-btn" onclick="submitAnswers()" disabled>Submit Answers</button>
    <span id="status"></span>
  </footer>
</div>

<script>
let gaps = [];

async function loadGaps() {
  document.getElementById('loading').style.display = 'block';
  try {
    const resp = await fetch('/gaps');
    gaps = await resp.json();
  } catch (e) {
    document.getElementById('status').textContent = 'Error loading questions: ' + e.message;
    document.getElementById('status').className = 'err';
    return;
  } finally {
    document.getElementById('loading').style.display = 'none';
  }
  renderGaps();
}

function renderGaps() {
  const container = document.getElementById('questions');
  container.innerHTML = '';
  gaps.forEach((gap, i) => {
    const card = document.createElement('div');
    card.className = 'gap-card';
    card.innerHTML = `
      <div class="gap-number">Question ${i + 1} of ${gaps.length}</div>
      <div class="gap-question">${escHtml(gap.question)}</div>
      <div class="options" id="opts-${i}"></div>
    `;
    const optsEl = card.querySelector(`#opts-${i}`);
    gap.options.forEach((opt, j) => {
      const lbl = document.createElement('label');
      lbl.className = 'option-label' + (j === gap.recommended_index ? ' recommended' : '');
      lbl.innerHTML = `
        <input type="radio" name="gap-${i}" value="${escHtml(opt)}" onchange="onSelect(this, ${i})">
        <span class="option-text">${escHtml(opt)}</span>
        ${j === gap.recommended_index ? '<span class="rec-badge">recommended</span>' : ''}
      `;
      optsEl.appendChild(lbl);
    });
    container.appendChild(card);
  });
  updateSubmitState();
}

function onSelect(radio, gapIndex) {
  // Highlight selected
  const opts = document.getElementById(`opts-${gapIndex}`).querySelectorAll('.option-label');
  opts.forEach(l => l.classList.remove('selected'));
  radio.parentElement.classList.add('selected');
  updateSubmitState();
}

function updateSubmitState() {
  const allAnswered = gaps.every((_, i) => {
    return document.querySelector(`input[name="gap-${i}"]:checked`) !== null;
  });
  document.getElementById('submit-btn').disabled = !allAnswered;
}

async function submitAnswers() {
  const answers = gaps.map((gap, i) => {
    const checked = document.querySelector(`input[name="gap-${i}"]:checked`);
    return { question: gap.question, chosen_option: checked ? checked.value : '' };
  });

  document.getElementById('submit-btn').disabled = true;
  document.getElementById('status').textContent = 'Submitting…';
  document.getElementById('status').className = '';

  try {
    const resp = await fetch('/answers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(answers),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    document.getElementById('questions').style.display = 'none';
    document.querySelector('footer').style.display = 'none';
    document.getElementById('done-msg').style.display = 'block';
  } catch (e) {
    document.getElementById('status').textContent = 'Error: ' + e.message;
    document.getElementById('status').className = 'err';
    document.getElementById('submit-btn').disabled = false;
  }
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function toggleTheme() {
  const isLight = document.documentElement.classList.contains('light');
  const next = isLight ? 'dark' : 'light';
  localStorage.setItem('maestro-gaps-theme', next);
  applyTheme(next);
}
function applyTheme(t) {
  if (t === 'light') {
    document.documentElement.classList.add('light');
    document.getElementById('theme-btn').textContent = '🌙 Dark';
  } else {
    document.documentElement.classList.remove('light');
    document.getElementById('theme-btn').textContent = '☀️ Light';
  }
}
applyTheme(localStorage.getItem('maestro-gaps-theme') || 'dark');
loadGaps();
</script>
</body>
</html>
```

- [ ] **Step 2: Verify static dir is included in package**

Check `pyproject.toml` has `include` or `package-data` for `sdlc/static/`. If using `hatchling` (default for this project), static files inside the package are included automatically if the directory is under `maestro/`.

```bash
grep -r "sdlc\|static\|include" pyproject.toml | grep -v "^#"
```

If no explicit include needed (hatchling auto-includes), proceed. If exclude patterns block it, add:
```toml
[tool.hatch.build.targets.wheel]
include = ["maestro/sdlc/static/*"]
```

- [ ] **Step 3: Commit**

```bash
git add maestro/sdlc/static/gaps.html
git commit -m "feat(sdlc): add gaps questionnaire HTML UI with dark/light theme"
```

---

## Task 5: Wire gaps resolution into the harness

**Files:**
- Modify: `maestro/sdlc/harness.py`
- Modify: `tests/test_sdlc_harness.py`

The harness must:
1. After generating the GAPS artifact, check if it contains any `[GAP]` items
2. If gaps exist: start GapsServer, open browser, block until answered, inject answers into prompt
3. Continue with artifacts 04–13 using enriched prompt

- [ ] **Step 1: Write the failing test**

Append to `tests/test_sdlc_harness.py`:

```python
def test_harness_resolves_gaps_and_enriches_prompt(tmp_path, monkeypatch):
    """Harness pauses at GAPS, resolves via mock server, enriches prompt."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch
    from maestro.sdlc.harness import DiscoveryHarness
    from maestro.sdlc.schemas import SDLCRequest, GapAnswer

    call_log: list[str] = []

    async def fake_generate(request, artifact_type):
        from maestro.sdlc.schemas import ArtifactType, SDLCArtifact, ARTIFACT_FILENAMES
        call_log.append(f"{artifact_type.value}:{request.prompt[-20:]}")
        content = "[GAP] Is SSO required?" if artifact_type == ArtifactType.GAPS else "# content"
        return SDLCArtifact(
            artifact_type=artifact_type,
            filename=ARTIFACT_FILENAMES[artifact_type],
            content=content,
        )

    mock_answers = [GapAnswer(question="Is SSO required?", chosen_option="Yes")]

    with patch.object(DiscoveryHarness, "_generate_artifact", new=fake_generate):
        with patch("maestro.sdlc.harness.resolve_gaps", return_value=mock_answers) as mock_resolve:
            harness = DiscoveryHarness(provider=object(), model="test")
            request = SDLCRequest(prompt="Build a CRM", workdir=str(tmp_path))
            result = asyncio.run(harness.arun(request))

    # resolve_gaps was called once
    mock_resolve.assert_called_once()
    # prompt was enriched for artifacts 04+
    prd_call = next(c for c in call_log if c.startswith("prd:"))
    assert "Is SSO required?" in "".join(call_log)
    assert result.artifact_count == 13
```

- [ ] **Step 2: Run to verify failure**

```
.venv/bin/pytest tests/test_sdlc_harness.py::test_harness_resolves_gaps_and_enriches_prompt -v
```
Expected: FAIL — `resolve_gaps` not defined yet.

- [ ] **Step 3: Add resolve_gaps function to gaps_server.py**

Append to `maestro/sdlc/gaps_server.py`:

```python
import webbrowser


def resolve_gaps(
    gaps_content: str,
    port: int = 4041,
    open_browser: bool = True,
) -> list[GapAnswer]:
    """Parse gaps from markdown, serve questionnaire, block until answered.

    Returns list of GapAnswer. Returns [] if no [GAP] items found.
    """
    items = parse_gaps(gaps_content)
    if not items:
        return []

    server = serve_gaps(items, port=port)
    url = f"http://localhost:{server.port}"
    if open_browser:
        webbrowser.open(url)

    answers = server.get_answers(timeout=None)  # block indefinitely
    server.stop()
    return answers or []
```

- [ ] **Step 4: Modify harness.py to call resolve_gaps after GAPS artifact**

Replace the loop section in `maestro/sdlc/harness.py` `arun` method:

```python
    async def arun(self, request: SDLCRequest) -> DiscoveryResult:
        """Generate all 13 artifacts and write them to spec/."""
        effective_prompt = request.prompt
        if request.brownfield:
            scan = self._scan_codebase(request.workdir)
            effective_prompt = f"{request.prompt}\n\n## Existing Codebase\n{scan}"

        effective_request = SDLCRequest(
            prompt=effective_prompt,
            language=request.language,
            brownfield=request.brownfield,
            workdir=request.workdir,
        )

        workdir = request.workdir if request.workdir != "." else self._workdir
        spec_dir = Path(workdir).resolve() / "spec"
        try:
            spec_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as exc:
            raise RuntimeError(
                f"Failed to create spec directory: {exc.strerror}"
            ) from exc

        from maestro.sdlc.writer import write_artifact
        from maestro.sdlc.gaps_server import resolve_gaps

        total = len(ARTIFACT_ORDER)
        artifacts: list[SDLCArtifact] = []

        for i, artifact_type in enumerate(ARTIFACT_ORDER, start=1):
            print(
                f"[{i}/{total}] Generating {artifact_type.value}...",
                file=sys.stderr,
                flush=True,
            )
            artifact = await self._generate_artifact(effective_request, artifact_type)
            artifacts.append(artifact)
            write_artifact(spec_dir, artifact)
            print(
                f"[{i}/{total}] ✓ {artifact.filename}",
                file=sys.stderr,
                flush=True,
            )

            # After GAPS: block until user answers via web UI
            if artifact_type == ArtifactType.GAPS and self._provider is not None:
                answers = resolve_gaps(artifact.content, port=self._gaps_port, open_browser=self._open_browser)
                if answers:
                    answers_text = "\n".join(
                        f"- {a.question} → {a.chosen_option}" for a in answers
                    )
                    effective_request = SDLCRequest(
                        prompt=f"{effective_request.prompt}\n\n## Gap Answers\n{answers_text}",
                        language=effective_request.language,
                        brownfield=effective_request.brownfield,
                        workdir=effective_request.workdir,
                    )

        result = DiscoveryResult(
            request=request,
            artifacts=artifacts,
            spec_dir=str(spec_dir),
        )
        return result
```

Also update `__init__` to accept `gaps_port` and `open_browser`:

```python
    def __init__(
        self,
        provider=None,
        model: str | None = None,
        workdir: str = ".",
        gaps_port: int = 4041,
        open_browser: bool = True,
    ) -> None:
        self._provider = provider
        self._model = model
        self._workdir = workdir
        self._gaps_port = gaps_port
        self._open_browser = open_browser
```

- [ ] **Step 5: Run harness test**

```
.venv/bin/pytest tests/test_sdlc_harness.py -v
```
Expected: all harness tests PASS.

- [ ] **Step 6: Commit**

```bash
git add maestro/sdlc/gaps_server.py maestro/sdlc/harness.py tests/test_sdlc_harness.py
git commit -m "feat(sdlc): wire gaps questionnaire into harness — blocking after artifact 03"
```

---

## Task 6: CLI updates (port flag + browser message)

**Files:**
- Modify: `maestro/cli.py`

- [ ] **Step 1: Add --gaps-port flag and update discover handler**

Find `_handle_discover` in `maestro/cli.py` (around line 510). The function signature and harness instantiation need:

1. Add `--gaps-port` CLI option (default `4041`)
2. Update the "gaps" message to tell user the URL
3. Pass `gaps_port` and `open_browser=True` to `DiscoveryHarness`

Find the discover command definition. It should look like:
```python
@cli.command("discover")
@click.option("--workdir", ...)
@click.option("--model", ...)
@click.option("--brownfield", ...)
...
```

Add after existing options:
```python
@click.option("--gaps-port", default=4041, show_default=True, help="Port for the gap questionnaire web UI.")
@click.option("--no-browser", is_flag=True, default=False, help="Do not auto-open browser for gap questionnaire.")
```

Update `_handle_discover` to print the blocking message:
```python
# Inside _handle_discover, replace the old gap message with:
print(
    f"  If gaps are found, a questionnaire will open at http://localhost:{gaps_port}\n"
    "  Answer all questions and click Submit to continue.\n",
    file=sys.stderr,
)
```

Pass to harness:
```python
harness = DiscoveryHarness(
    provider=provider,
    model=model_name,
    workdir=workdir,
    gaps_port=gaps_port,
    open_browser=not no_browser,
)
```

- [ ] **Step 2: Run the full test suite**

```
.venv/bin/pytest tests/ -v --tb=short
```
Expected: all existing tests pass + new tests pass.

- [ ] **Step 3: Commit**

```bash
git add maestro/cli.py
git commit -m "feat(sdlc): add --gaps-port and --no-browser CLI flags for gap questionnaire"
```

---

## Task 7: Final verification

- [ ] **Step 1: Run full test suite**

```
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
.venv/bin/pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: all tests pass, 0 failures.

- [ ] **Step 2: Quick smoke test (stub mode)**

```bash
.venv/bin/maestro discover "Build a SaaS CRM for B2B sales teams" --no-browser
```
Expected: generates 03-gaps.md, then since `provider=None` in stub mode, no gaps UI triggered (only triggers when provider is set). Should generate all 13 artifacts with stubs.

- [ ] **Step 3: Commit state update**

Update `STATE.md` Quick Tasks table with this task, then:
```bash
git add STATE.md
git commit -m "chore: mark sdlc-gaps-web-ui quick task complete in STATE.md"
```
