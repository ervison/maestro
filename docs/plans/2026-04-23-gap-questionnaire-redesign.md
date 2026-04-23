# Gap Questionnaire Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the heuristic-only single-choice gap questionnaire with an LLM-enriched questionnaire that supports `single`/`multiple` selection modes and optional free-text — so users can answer gap questions meaningfully and the pipeline resumes with richer context.

**Architecture:** `GapItem` gains `selection_mode`, `allow_free_text`, `free_text_placeholder`, `recommended_options`. A new `enrich_gap_items()` async function calls the LLM once per gap to populate these fields, with a heuristic fallback. `GapAnswer` gains `selected_options: list[str]` and `free_text: str`. `GapsServer` serializes the new fields over `/gaps` and parses the new payload from `/answers`. `gaps.html` renders radio/checkbox/textarea and enforces: single → exactly 1; multiple → at least 1. Harness passes provider/model into `resolve_gaps`.

**Tech Stack:** Python 3.12, dataclasses, asyncio, httpx (existing provider streaming), stdlib ThreadingHTTPServer, vanilla JS (no framework in gaps.html).

---

## File map

| File | Change |
|------|--------|
| `maestro/sdlc/schemas.py` | Extend `GapItem`, replace `GapAnswer.chosen_option` with `selected_options + free_text` |
| `maestro/sdlc/gaps_server.py` | Add `enrich_gap_items()`, update `_serve_gaps_json`, `_receive_answers`, `resolve_gaps` signature |
| `maestro/sdlc/harness.py` | Pass `provider`, `model` to `resolve_gaps`; update answers_text formatter |
| `maestro/sdlc/static/gaps.html` | Full rewrite of JS render/submit for radio+checkbox+textarea |
| `tests/test_sdlc_gaps_server.py` | Update existing + add new tests for schema, enrichment, server round-trip |
| `tests/test_sdlc_harness.py` | Update answers_text formatting assertion |
| `tests/test_sdlc_schemas.py` | Update GapItem/GapAnswer construction tests |

---

## Task 1: Extend schemas — GapItem and GapAnswer

**Files:**
- Modify: `maestro/sdlc/schemas.py:136-149`
- Test: `tests/test_sdlc_schemas.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_sdlc_schemas.py  (add to existing file or create if missing)
def test_gap_item_defaults():
    from maestro.sdlc.schemas import GapItem
    item = GapItem(question="Is SSO required?", options=["Yes", "No"])
    assert item.selection_mode == "single"
    assert item.allow_free_text is False
    assert item.free_text_placeholder == ""
    assert item.recommended_options == []
    assert item.recommended_index == 0

def test_gap_answer_new_fields():
    from maestro.sdlc.schemas import GapAnswer
    ans = GapAnswer(question="Is SSO required?", selected_options=["Yes"])
    assert ans.selected_options == ["Yes"]
    assert ans.free_text == ""

def test_gap_answer_rejects_empty_selected():
    from maestro.sdlc.schemas import GapAnswer
    import pytest
    with pytest.raises((ValueError, TypeError)):
        GapAnswer(question="q", selected_options=[])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
python -m pytest tests/test_sdlc_schemas.py -v 2>&1 | tail -20
```
Expected: FAIL (GapItem missing `selection_mode`, GapAnswer missing `selected_options`)

- [ ] **Step 3: Update `maestro/sdlc/schemas.py`**

Replace the existing `GapItem` and `GapAnswer` dataclasses (lines 136–149) with:

```python
from typing import Literal

@dataclass
class GapItem:
    """A single gap question with answer options and UI metadata."""

    question: str
    options: list[str]
    selection_mode: Literal["single", "multiple"] = "single"
    recommended_index: int = 0
    recommended_options: list[str] = field(default_factory=list)
    allow_free_text: bool = False
    free_text_placeholder: str = ""


@dataclass
class GapAnswer:
    """User's answer to a single gap question."""

    question: str
    selected_options: list[str]
    free_text: str = ""

    def __post_init__(self) -> None:
        if not self.selected_options:
            raise ValueError("selected_options must have at least one item")
```

Also add `from typing import Literal` at top if not present (it's already `from __future__ import annotations` so just add to imports).

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
python -m pytest tests/test_sdlc_schemas.py -v 2>&1 | tail -20
```
Expected: PASS

- [ ] **Step 5: Run full suite to check regressions**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
python -m pytest tests/ -v 2>&1 | tail -30
```
Note failures — they are expected from gaps_server/harness that use old fields. Fix in subsequent tasks.

- [ ] **Step 6: Commit**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
git add maestro/sdlc/schemas.py tests/test_sdlc_schemas.py
git commit -m "feat(schemas): extend GapItem/GapAnswer for multi-select and free-text"
```

---

## Task 2: Add `enrich_gap_items()` + update `_infer_options` fallback

**Files:**
- Modify: `maestro/sdlc/gaps_server.py`
- Test: `tests/test_sdlc_gaps_server.py`

**Context:** `enrich_gap_items` calls the provider once per gap with a structured prompt that asks the model to return JSON: `{"selection_mode": "single"|"multiple", "options": [...], "recommended_options": [...], "allow_free_text": bool, "free_text_placeholder": str}`. On any error (provider=None, network, parse error) it falls back to `_infer_options_as_gap_item()`.

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/test_sdlc_gaps_server.py

import asyncio
import pytest

def test_enrich_gap_items_no_provider_uses_fallback():
    """Without a provider, enrichment uses heuristic fallback."""
    from maestro.sdlc.gaps_server import enrich_gap_items
    from maestro.sdlc.schemas import GapItem
    items = [GapItem(question="Is SSO required?", options=[])]
    result = asyncio.run(enrich_gap_items(items, provider=None, model=None, context=""))
    assert len(result) == 1
    assert len(result[0].options) >= 2
    assert result[0].selection_mode in ("single", "multiple")

def test_enrich_gap_items_provider_returns_valid_json():
    """Provider response is parsed into GapItem fields."""
    from maestro.sdlc.gaps_server import enrich_gap_items
    from maestro.sdlc.schemas import GapItem

    class FakeProvider:
        async def stream(self, messages, model=None, **kw):
            payload = '{"selection_mode":"multiple","options":["REST","GraphQL","gRPC"],"recommended_options":["REST"],"allow_free_text":false,"free_text_placeholder":""}'
            yield type("Msg", (), {"content": payload, "tool_calls": None})()

    items = [GapItem(question="Which API protocols are needed?", options=[])]
    result = asyncio.run(enrich_gap_items(items, provider=FakeProvider(), model="x", context="API project"))
    assert result[0].selection_mode == "multiple"
    assert "REST" in result[0].options

def test_enrich_gap_items_provider_bad_json_uses_fallback():
    """Provider returning invalid JSON falls back gracefully."""
    from maestro.sdlc.gaps_server import enrich_gap_items
    from maestro.sdlc.schemas import GapItem

    class BadProvider:
        async def stream(self, messages, model=None, **kw):
            yield type("Msg", (), {"content": "not json at all", "tool_calls": None})()

    items = [GapItem(question="Is mobile app required?", options=[])]
    result = asyncio.run(enrich_gap_items(items, provider=BadProvider(), model="x", context=""))
    assert len(result[0].options) >= 2  # fallback provided options
```

- [ ] **Step 2: Run tests to fail**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
python -m pytest tests/test_sdlc_gaps_server.py::test_enrich_gap_items_no_provider_uses_fallback -v 2>&1 | tail -10
```
Expected: FAIL (function not found)

- [ ] **Step 3: Implement `enrich_gap_items` in `gaps_server.py`**

Add this block after the `_looks_portuguese` function (before `_extract_inline_alternatives`):

```python
import json as _json

_ENRICH_SYSTEM = """\
You are a requirements analyst. Given a gap question from an SDLC discovery session, \
return a JSON object (no markdown, raw JSON only) with exactly these fields:
- selection_mode: "single" if the question has one correct answer, "multiple" if several can apply simultaneously
- options: array of 3-6 short, concrete, mutually-understandable answer strings (NOT sentence fragments of the question itself)
- recommended_options: array with 0-2 options you consider most common/default
- allow_free_text: true if the question is open-ended enough to need a custom answer
- free_text_placeholder: short placeholder string for the textarea when allow_free_text is true, else ""

Rules:
- Each option must be a standalone phrase a user can select without reading the question again
- Do NOT split the question sentence into fragments as options
- Use the project context to make options domain-relevant
- Respond with ONLY the JSON object, no explanation, no markdown fences
"""

_ENRICH_USER_TMPL = """\
Project context: {context}

Gap question: {question}
"""


async def enrich_gap_items(
    items: list["GapItem"],
    provider: Any,
    model: str | None,
    context: str,
) -> list["GapItem"]:
    """Enrich gap items with LLM-generated options and UI metadata.

    Falls back to heuristic if provider is None or returns unparseable content.
    """
    enriched: list[GapItem] = []
    for item in items:
        if provider is None:
            enriched.append(_heuristic_enrich(item))
            continue
        try:
            enriched.append(await _llm_enrich(item, provider, model, context))
        except Exception:
            enriched.append(_heuristic_enrich(item))
    return enriched


async def _llm_enrich(
    item: "GapItem",
    provider: Any,
    model: str | None,
    context: str,
) -> "GapItem":
    messages = [
        {"role": "system", "content": _ENRICH_SYSTEM},
        {"role": "user", "content": _ENRICH_USER_TMPL.format(context=context, question=item.question)},
    ]
    collected = ""
    async for msg in provider.stream(messages, model=model):
        if msg.content:
            collected += msg.content

    data = _json.loads(collected.strip())
    return GapItem(
        question=item.question,
        options=[str(o) for o in data.get("options", [])],
        selection_mode=data.get("selection_mode", "single"),
        recommended_index=0,
        recommended_options=[str(o) for o in data.get("recommended_options", [])],
        allow_free_text=bool(data.get("allow_free_text", False)),
        free_text_placeholder=str(data.get("free_text_placeholder", "")),
    )


def _heuristic_enrich(item: "GapItem") -> "GapItem":
    """Apply heuristic option inference and wrap into a full GapItem."""
    options = _infer_options(item.question)
    q_lower = item.question.lower()
    open_prefixes = (
        "what ", "which ", "how ", "when ", "where ", "why ", "who ",
        "quem ", "qual ", "quais ", "como ", "quanto ", "quantos ",
        "quantas ", "quando ", "onde ", "por que ", "o que ",
    )
    allow_free = any(q_lower.startswith(p) for p in open_prefixes)
    multi_keywords = (
        "quais ", "which ", "select all", "pode ser mais", "podem ser",
        "list ", "listar", "technologies", "tecnologias", "protocols",
        "protocolos", "features", "funcionalidades",
    )
    is_multi = any(kw in q_lower for kw in multi_keywords)
    return GapItem(
        question=item.question,
        options=options,
        selection_mode="multiple" if is_multi else "single",
        recommended_index=0,
        recommended_options=[],
        allow_free_text=allow_free,
        free_text_placeholder="Especifique..." if _looks_portuguese(item.question) else "Specify...",
    )
```

Also update `parse_gaps()` to create items with empty `options=[]` (enrichment fills them):
```python
# In parse_gaps(), the GapItem creation stays the same but options comes from _infer_options for now
# enrich_gap_items is called separately from resolve_gaps
```

- [ ] **Step 4: Run tests to pass**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
python -m pytest tests/test_sdlc_gaps_server.py -v 2>&1 | tail -20
```
Expected: all new tests PASS; old tests still pass

- [ ] **Step 5: Commit**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
git add maestro/sdlc/gaps_server.py tests/test_sdlc_gaps_server.py
git commit -m "feat(gaps): add enrich_gap_items with LLM enrichment and heuristic fallback"
```

---

## Task 3: Update GapsServer API — serialization + answer parsing

**Files:**
- Modify: `maestro/sdlc/gaps_server.py` — `_serve_gaps_json`, `_receive_answers`, `resolve_gaps`
- Test: `tests/test_sdlc_gaps_server.py`

- [ ] **Step 1: Write failing HTTP round-trip test**

```python
# Add to tests/test_sdlc_gaps_server.py

def test_gaps_json_endpoint_includes_new_fields():
    """GET /gaps returns selection_mode, allow_free_text, recommended_options."""
    from maestro.sdlc.gaps_server import GapsServer
    from maestro.sdlc.schemas import GapItem

    items = [
        GapItem(
            question="Which protocols are needed?",
            options=["REST", "GraphQL"],
            selection_mode="multiple",
            allow_free_text=False,
            recommended_options=["REST"],
        )
    ]
    server = GapsServer(items, port=0)
    server.start()
    try:
        import urllib.request
        resp = urllib.request.urlopen(f"http://127.0.0.1:{server.port}/gaps")
        data = json.loads(resp.read())
        assert data[0]["selection_mode"] == "multiple"
        assert data[0]["allow_free_text"] is False
        assert data[0]["recommended_options"] == ["REST"]
    finally:
        server.stop()

def test_answers_endpoint_parses_selected_options():
    """POST /answers with selected_options list returns 200 and sets answers."""
    import threading, urllib.request
    from maestro.sdlc.gaps_server import GapsServer
    from maestro.sdlc.schemas import GapItem

    items = [GapItem(question="Which protocols?", options=["REST", "GraphQL"], selection_mode="multiple")]
    server = GapsServer(items, port=0)
    server.start()
    try:
        payload = json.dumps([
            {"question": "Which protocols?", "selected_options": ["REST", "GraphQL"], "free_text": ""}
        ]).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.port}/answers",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req)
        assert resp.status == 200
        answers = server.get_answers(timeout=1.0)
        assert answers is not None
        assert answers[0].selected_options == ["REST", "GraphQL"]
        assert answers[0].free_text == ""
    finally:
        server.stop()
```

- [ ] **Step 2: Run tests to fail**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
python -m pytest tests/test_sdlc_gaps_server.py::test_gaps_json_endpoint_includes_new_fields -v 2>&1 | tail -10
```

- [ ] **Step 3: Update `_serve_gaps_json` in `gaps_server.py`**

Replace the payload dict in `_serve_gaps_json`:
```python
def _serve_gaps_json(self) -> None:
    payload = [
        {
            "question": item.question,
            "options": item.options,
            "selection_mode": item.selection_mode,
            "recommended_index": item.recommended_index,
            "recommended_options": item.recommended_options,
            "allow_free_text": item.allow_free_text,
            "free_text_placeholder": item.free_text_placeholder,
        }
        for item in server_ref._items
    ]
    body = json.dumps(payload).encode("utf-8")
    # ... rest unchanged
```

- [ ] **Step 4: Update `_receive_answers` in `gaps_server.py`**

Replace the answer parsing block:
```python
def _receive_answers(self) -> None:
    length = int(self.headers.get("Content-Length", 0))
    raw = self.rfile.read(length)
    try:
        data: list[dict] = json.loads(raw)
        answers = [
            GapAnswer(
                question=item["question"],
                selected_options=item.get("selected_options") or [item.get("chosen_option", "")],
                free_text=item.get("free_text", ""),
            )
            for item in data
        ]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        self.send_error(400, "Invalid JSON")
        return
    # ... rest unchanged
```

Note: `item.get("selected_options") or [item.get("chosen_option", "")]` keeps backward compat with old payloads sending `chosen_option`.

- [ ] **Step 5: Update `resolve_gaps` signature**

```python
async def resolve_gaps(
    gaps_content: str,
    provider: Any = None,
    model: str | None = None,
    port: int = 4041,
    open_browser: bool = True,
) -> list[GapAnswer]:
    """Parse gaps from markdown, enrich with LLM, serve questionnaire, block until answered."""
    items = parse_gaps(gaps_content)
    if not items:
        return []

    items = await enrich_gap_items(items, provider=provider, model=model, context=gaps_content[:500])

    server = serve_gaps(items, port=port)
    url = f"http://localhost:{server.port}"
    if open_browser:
        webbrowser.open(url)

    try:
        answers = server.get_answers(timeout=None)
    finally:
        server.stop()

    return answers or []
```

Note: `resolve_gaps` becomes `async def` — callers must `await` it.

- [ ] **Step 6: Run tests to pass**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
python -m pytest tests/test_sdlc_gaps_server.py -v 2>&1 | tail -20
```

- [ ] **Step 7: Commit**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
git add maestro/sdlc/gaps_server.py tests/test_sdlc_gaps_server.py
git commit -m "feat(gaps-server): serialize new GapItem fields and parse selected_options from answers"
```

---

## Task 4: Update `harness.py` — pass provider/model to resolve_gaps + fix answers_text

**Files:**
- Modify: `maestro/sdlc/harness.py:88-103`
- Test: `tests/test_sdlc_harness.py`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/test_sdlc_harness.py

def test_harness_formats_answers_with_selected_options():
    """answers_text uses selected_options joined with comma."""
    # This tests the formatting inline in arun — simplest via integration:
    # We just verify the prompt appended has the new format
    from maestro.sdlc.schemas import GapAnswer
    answers = [
        GapAnswer(question="Which protocols?", selected_options=["REST", "GraphQL"], free_text=""),
        GapAnswer(question="Is SSO required?", selected_options=["Yes"], free_text="via SAML"),
    ]
    # Simulate the formatter
    lines = []
    for a in answers:
        opts_str = ", ".join(a.selected_options)
        line = f"- {a.question} → {opts_str}"
        if a.free_text:
            line += f" ({a.free_text})"
        lines.append(line)
    text = "\n".join(lines)
    assert "REST, GraphQL" in text
    assert "via SAML" in text
```

- [ ] **Step 2: Run test to fail**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
python -m pytest tests/test_sdlc_harness.py::test_harness_formats_answers_with_selected_options -v 2>&1 | tail -10
```

- [ ] **Step 3: Update harness.py gap-answers block**

Replace lines 87–103 in `harness.py`:
```python
if artifact_type == ArtifactType.GAPS and self._provider is not None:
    answers = await resolve_gaps(
        artifact.content,
        provider=self._provider,
        model=self._model,
        port=self._gaps_port,
        open_browser=self._open_browser,
    )
    if answers:
        answers_lines = []
        for answer in answers:
            opts_str = ", ".join(answer.selected_options)
            line = f"- {answer.question} → {opts_str}"
            if answer.free_text:
                line += f" (note: {answer.free_text})"
            answers_lines.append(line)
        answers_text = "\n".join(answers_lines)
        effective_request = SDLCRequest(
            prompt=f"{effective_request.prompt}\n\n## Gap Answers\n{answers_text}",
            language=effective_request.language,
            brownfield=effective_request.brownfield,
            workdir=effective_request.workdir,
        )
```

Also update the import at top of harness.py:
```python
from maestro.sdlc.gaps_server import resolve_gaps
```
(This import is already there; just verify it stays as-is — `resolve_gaps` is now async, called with `await`.)

- [ ] **Step 4: Run tests**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
python -m pytest tests/test_sdlc_harness.py -v 2>&1 | tail -20
```

- [ ] **Step 5: Commit**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
git add maestro/sdlc/harness.py tests/test_sdlc_harness.py
git commit -m "feat(harness): pass provider/model to resolve_gaps and format multi-select answers"
```

---

## Task 5: Rewrite `gaps.html` — radio/checkbox/textarea + validation

**Files:**
- Modify: `maestro/sdlc/static/gaps.html` (full rewrite of renderGaps/submitAnswers JS, keep existing CSS)

**Contract:**
- `single` → `<input type="radio">`, exactly 1 must be checked to enable submit
- `multiple` → `<input type="checkbox">`, at least 1 must be checked to enable submit
- `allow_free_text=true` → show `<textarea>` below the options for that card
- Recommended options: highlight them with `rec-badge` (can still apply to checkbox)
- Submit payload: `[{question, selected_options: [...], free_text: ""}]`
- Backward compat removed — only `selected_options` format

- [ ] **Step 1: No unit test here — tested via MCP in Task 7. Just verify the HTML renders correctly.**

- [ ] **Step 2: Replace the `<script>` block in `gaps.html`**

The new script must:
1. Load gaps from `/gaps` (same as before)
2. Render each card with radio or checkbox based on `gap.selection_mode`
3. Show a `<textarea>` when `gap.allow_free_text === true`
4. Highlight recommended options (those whose text is in `gap.recommended_options`)
5. `updateSubmitState()` checks: for each gap, at least 1 option selected
6. `submitAnswers()` collects `selected_options` as array, `free_text` from textarea

Replace the JS `renderGaps` function entirely:

```javascript
function renderGaps() {
  const container = document.getElementById('questions');
  container.innerHTML = '';
  gaps.forEach((gap, i) => {
    const inputType = gap.selection_mode === 'multiple' ? 'checkbox' : 'radio';
    const card = document.createElement('div');
    card.className = 'gap-card';

    let optionsHtml = '';
    gap.options.forEach((opt, j) => {
      const isRec = gap.recommended_options && gap.recommended_options.includes(opt);
      const recBadge = isRec ? '<span class="rec-badge">recommended</span>' : '';
      const recClass = isRec ? ' recommended' : '';
      optionsHtml += `
        <label class="option-label${recClass}" id="lbl-${i}-${j}">
          <input type="${inputType}" name="gap-${i}" value="${escHtml(opt)}"
                 onchange="onSelect(this, ${i})">
          <span class="option-text">${escHtml(opt)}</span>
          ${recBadge}
        </label>`;
    });

    const textareaHtml = gap.allow_free_text ? `
      <textarea id="free-${i}" class="free-text"
        placeholder="${escHtml(gap.free_text_placeholder || 'Optional — add details...')}"
        rows="2"></textarea>` : '';

    const modeHint = gap.selection_mode === 'multiple'
      ? '<span class="mode-hint">Select all that apply</span>'
      : '';

    card.innerHTML = `
      <div class="gap-number">Question ${i + 1} of ${gaps.length}</div>
      <div class="gap-question">${escHtml(gap.question)}</div>
      ${modeHint}
      <div class="options" id="opts-${i}">${optionsHtml}</div>
      ${textareaHtml}
    `;
    container.appendChild(card);
  });
  updateSubmitState();
}
```

Also update `onSelect`, `updateSubmitState`, and `submitAnswers`:

```javascript
function onSelect(input, gapIndex) {
  const opts = document.getElementById(`opts-${gapIndex}`).querySelectorAll('.option-label');
  if (input.type === 'radio') {
    opts.forEach(l => l.classList.remove('selected'));
    input.parentElement.classList.add('selected');
  } else {
    input.parentElement.classList.toggle('selected', input.checked);
  }
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
    const checked = [...document.querySelectorAll(`input[name="gap-${i}"]:checked`)];
    const freeEl = document.getElementById(`free-${i}`);
    return {
      question: gap.question,
      selected_options: checked.map(c => c.value),
      free_text: freeEl ? freeEl.value.trim() : '',
    };
  });
  // ... rest of submit unchanged (fetch /answers, show done-msg)
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
```

Add CSS for `free-text` and `mode-hint` to the existing `<style>` block:

```css
.free-text {
  width: 100%;
  margin-top: 10px;
  background: var(--bg);
  border: 1.5px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
  padding: 8px 12px;
  resize: vertical;
}
.free-text:focus { outline: none; border-color: var(--accent); }
.mode-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 10px;
  display: block;
}
```

- [ ] **Step 3: Verify static HTML is valid**

```bash
python3 -c "
from pathlib import Path
html = Path('maestro/sdlc/static/gaps.html').read_text()
assert 'type=\"checkbox\"' in html or 'selection_mode' in html
assert 'selected_options' in html
assert 'free_text' in html
print('HTML checks passed')
"
```

- [ ] **Step 4: Commit**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
git add maestro/sdlc/static/gaps.html
git commit -m "feat(ui): redesign gaps.html with radio/checkbox/textarea and new payload format"
```

---

## Task 6: Run full test suite and fix any regressions

**Files:** Various test files

- [ ] **Step 1: Run all tests**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
python -m pytest tests/ -v 2>&1 | tee /tmp/test_results.txt | tail -40
```

- [ ] **Step 2: Fix any failures**

Common expected failures after schema change:
- `test_sdlc_gaps_server.py` tests using old `chosen_option` field → update to `selected_options`
- `test_sdlc_harness.py` tests checking `answer.chosen_option` → update to `answer.selected_options[0]`
- Any test creating `GapAnswer(question=..., chosen_option=...)` → update to `selected_options=[...]`

For each failure, fix the test to use the new API. Do NOT change production code to match broken tests.

- [ ] **Step 3: Run until all pass**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
python -m pytest tests/ -v 2>&1 | tail -10
```
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
git add tests/
git commit -m "fix(tests): update test assertions for new GapItem/GapAnswer schema"
```

---

## Task 7: E2E test via MCP browser

**Prerequisite:** All tasks 1–6 complete, all tests passing.

- [ ] **Step 1: Start a discover run in background**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
mkdir -p testes/spec
nohup python -m maestro discover "Sistema de agendamento de consultas médicas para clínica pequena. Pacientes podem agendar, reagendar e cancelar consultas online. Médicos gerenciam sua agenda." --output testes/spec > /tmp/maestro_e2e_mcp.log 2>&1 &
echo "PID: $!"
```

- [ ] **Step 2: Wait for server to start**

```bash
sleep 15 && curl -s http://127.0.0.1:4041/gaps | python3 -m json.tool | head -40
```
Expected: JSON array with gap items including `selection_mode`, `allow_free_text`, `options`.

- [ ] **Step 3: Open browser via MCP and take snapshot**

Use `chrome-devtools_navigate_page` to open `http://127.0.0.1:4041/` and `chrome-devtools_take_snapshot` to verify:
- Questions are rendered
- At least one uses checkbox (multiple)
- At least one has a textarea (allow_free_text)
- Submit button is disabled

- [ ] **Step 4: Answer questions and submit**

Use MCP to:
1. Click at least one checkbox/radio per question
2. Fill textarea on free-text questions
3. Verify submit button enables
4. Click submit
5. Verify done message appears

- [ ] **Step 5: Wait for pipeline to finish**

```bash
sleep 60 && ls -la testes/spec/
```
Expected: 13 `.md` files present.

- [ ] **Step 6: Verify all 13 artifacts**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
ls testes/spec/*.md | wc -l
# Must be 13
for f in testes/spec/*.md; do echo "=== $f ===" && head -3 "$f"; done
```

- [ ] **Step 7: Commit final state if artifacts are correct**

```bash
cd /home/ervison/Documents/PROJETOS/labs/timeIA/maestro
git add -A
git commit -m "feat: gap questionnaire redesign complete — LLM enrichment, multi-select, free-text"
```
