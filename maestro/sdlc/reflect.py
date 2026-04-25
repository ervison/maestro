"""SDLC Reflect Loop — iterative LLM-based quality evaluation and correction."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from maestro.sdlc.schemas import (
    ReflectCorrection,
    ReflectCycle,
    ReflectDimensionScore,
    ReflectReport,
)

DIMENSIONS = [
    "Cobertura de domínio",
    "Consistência de nomenclatura",
    "Alinhamento modelo ↔ API",
    "Cobertura de RN em ACs",
    "Coerência PRD ↔ técnico",
    "Qualidade dos ADRs",
    "Plano de testes vs. escopo",
    "Qualidade individual",
    "Rastreabilidade (gaps → decisões)",
    "Integridade dos artefatos",
    "Cobertura de requisitos não-funcionais (NFR)",
]

TARGET_MEAN = 8.0


def _extract_json(text: str) -> Any:
    """Extract JSON from text, handling ```json ... ``` fences."""
    # Try to find a JSON code block first
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        candidate = fence_match.group(1).strip()
        return json.loads(candidate)
    # Fallback: try to parse entire text as JSON
    return json.loads(text.strip())


class ReflectLoop:
    """Iterative quality evaluation loop for generated SDLC artifacts."""

    def _read_spec_files(self, spec_dir: Path) -> dict[str, str]:
        """Read all *.md files from spec_dir. Returns {filename: content}."""
        result: dict[str, str] = {}
        for md_file in sorted(spec_dir.glob("*.md")):
            try:
                result[md_file.name] = md_file.read_text(encoding="utf-8")
            except OSError as exc:
                print(
                    f"[reflect] Warning: could not read {md_file.name}: {exc}",
                    file=sys.stderr,
                )
        return result

    def _build_eval_prompt(self, spec_contents: dict[str, str]) -> str:
        """Build the evaluation prompt for STEP 1+2."""
        files_section = "\n\n".join(
            f"=== {fname} ===\n{content}" for fname, content in spec_contents.items()
        )
        dimensions_list = "\n".join(
            f"{i + 1}. {d}" for i, d in enumerate(DIMENSIONS)
        )
        return f"""You are a senior software architect reviewing a set of SDLC specification artifacts.

Evaluate the following spec files across {len(DIMENSIONS)} quality dimensions, then identify the top-3 most important problems to fix.

## Dimensions (score 0-10 each)
{dimensions_list}

## Spec Files
{files_section}

## Instructions
Respond ONLY with a JSON object in this exact format:
```json
{{
  "scores": [
    {{"dimension": "<dimension name>", "score": <float 0-10>, "justification": "<one sentence>"}}
  ],
  "problems": [
    {{"file": "<filename>", "dimension": "<dimension name>", "what_to_change": "<concrete description>"}}
  ]
}}
```
The "scores" array must contain exactly {len(DIMENSIONS)} entries, one per dimension.
The "problems" array must contain at most 3 entries focusing on the most impactful issues.
Do not include any text outside the JSON block."""

    def _build_fix_prompt(
        self, spec_contents: dict[str, str], problems: list[dict[str, str]]
    ) -> str:
        """Build the correction prompt for STEP 3."""
        problems_text = "\n".join(
            f"- File: {p['file']} | Dimension: {p['dimension']} | Change: {p['what_to_change']}"
            for p in problems
        )
        files_section = "\n\n".join(
            f"=== {fname} ===\n{content}" for fname, content in spec_contents.items()
        )
        return f"""You are a senior software architect making targeted corrections to SDLC specification files.

## Problems to fix
{problems_text}

## Current Spec Files
{files_section}

## Instructions
For each problem, produce a minimal surgical patch: find an exact substring in the target file and replace it with the improved version.

Respond ONLY with a JSON array of patch objects:
```json
[
  {{
    "file": "<filename>",
    "old": "<exact substring to replace — must exist verbatim in the file>",
    "new": "<replacement text>"
  }}
]
```
Rules:
- "old" must be an EXACT substring found verbatim in the file (copy-paste from the file content above).
- Keep patches minimal — change only what is necessary.
- Do not include patches for files not listed in the problems.
- Do not include any text outside the JSON block."""

    def _apply_patches(
        self, spec_dir: Path, patches: list[dict[str, str]]
    ) -> list[tuple[str, str]]:
        """Apply old→new patches to files. Returns list of (file, description) applied."""
        applied: list[tuple[str, str]] = []
        for patch in patches:
            fname = patch.get("file", "")
            old = patch.get("old", "")
            new = patch.get("new", "")
            if not fname or not old:
                print(
                    f"[reflect] Warning: skipping malformed patch (missing file or old): {patch}",
                    file=sys.stderr,
                )
                continue
            target = (spec_dir / fname).resolve()
            spec_root = spec_dir.resolve()
            try:
                target.relative_to(spec_root)
            except ValueError as exc:
                raise RuntimeError(f"Patch target escapes spec_dir: {fname}") from exc
            if not target.exists():
                print(
                    f"[reflect] Warning: patch target not found: {fname}",
                    file=sys.stderr,
                )
                continue
            content = target.read_text(encoding="utf-8")
            if old not in content:
                print(
                    f"[reflect] Warning: patch 'old' string not found in {fname} — skipping",
                    file=sys.stderr,
                )
                continue
            updated = content.replace(old, new, 1)
            target.write_text(updated, encoding="utf-8")
            applied.append((fname, f"replaced '{old[:40]}...' in {fname}"))
        return applied

    async def _call_provider(self, provider: Any, model: str | None, prompt: str) -> str:
        """Call the provider and collect the full response text."""
        from maestro.providers.base import Message

        messages = [
            Message(role="user", content=prompt),
        ]
        parts: list[str] = []
        async for msg in provider.stream(messages, tools=None, model=model):
            if isinstance(msg, str):
                parts.append(msg)
            elif hasattr(msg, "role") and msg.role == "assistant" and msg.content:
                parts = [msg.content]
        return "".join(parts).strip()

    async def run(
        self,
        provider: Any,
        model: str | None,
        spec_dir: Path,
        max_cycles: int = 5,
    ) -> ReflectReport:
        """Run the reflect loop. Returns a ReflectReport."""
        cycles: list[ReflectCycle] = []

        for cycle_num in range(1, max_cycles + 1):
            # Step 1: Read current spec files
            spec_contents = self._read_spec_files(spec_dir)

            # Step 2: Evaluate
            eval_prompt = self._build_eval_prompt(spec_contents)
            try:
                eval_response = await self._call_provider(provider, model, eval_prompt)
                eval_data = _extract_json(eval_response)
                raw_scores = eval_data.get("scores", [])
                raw_problems = eval_data.get("problems", [])
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                print(
                    f"[reflect] Cycle {cycle_num}/{max_cycles} — malformed eval JSON ({exc}), skipping",
                    file=sys.stderr,
                )
                cycles.append(ReflectCycle(cycle=cycle_num, mean=0.0))
                continue

            # Build dimension scores
            dim_scores: list[ReflectDimensionScore] = []
            for s in raw_scores:
                try:
                    dim_scores.append(
                        ReflectDimensionScore(
                            dimension=s["dimension"],
                            score=float(s["score"]),
                            justification=s.get("justification", ""),
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    pass

            mean = sum(s.score for s in dim_scores) / len(dim_scores) if dim_scores else 0.0
            print(
                f"[reflect] Cycle {cycle_num}/{max_cycles} — mean: {mean:.1f}/10",
                file=sys.stderr,
                flush=True,
            )

            cycle = ReflectCycle(cycle=cycle_num, scores=dim_scores, mean=mean)
            cycles.append(cycle)

            if mean >= TARGET_MEAN:
                return ReflectReport(cycles=cycles, final_mean=mean, passed=True)

            # Step 3: Apply corrections if not last cycle
            if cycle_num == max_cycles:
                break

            fix_prompt = self._build_fix_prompt(spec_contents, raw_problems)
            try:
                fix_response = await self._call_provider(provider, model, fix_prompt)
                patches = _extract_json(fix_response)
                if not isinstance(patches, list):
                    raise ValueError("patches must be a JSON array")
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                print(
                    f"[reflect] Cycle {cycle_num}/{max_cycles} — malformed fix JSON ({exc}), skipping patches",
                    file=sys.stderr,
                )
                continue

            applied = self._apply_patches(spec_dir, patches)
            for fname, description in applied:
                # Find the relevant dimension from problems
                dimension = next(
                    (p.get("dimension", "") for p in raw_problems if p.get("file") == fname),
                    "",
                )
                cycle.corrections.append(
                    ReflectCorrection(
                        cycle=cycle_num,
                        file=fname,
                        dimension=dimension,
                        description=description,
                    )
                )

        final_mean = cycles[-1].mean if cycles else 0.0
        return ReflectReport(cycles=cycles, final_mean=final_mean, passed=False)


async def run_reflect_loop(
    provider: Any,
    model: str | None,
    spec_dir: Path,
    max_cycles: int = 5,
) -> ReflectReport:
    """Convenience entry point for running the reflect loop."""
    loop = ReflectLoop()
    return await loop.run(provider=provider, model=model, spec_dir=spec_dir, max_cycles=max_cycles)
