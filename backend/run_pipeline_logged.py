r"""
Runs the real semantic pipeline (Components 1-7) with the real Ollama model,
keeps the terminal clean, and saves everything to a folder.

Put this file in your backend\ folder and run from there:

    python run_pipeline_logged.py C:\mw\miniwallet-buggy --label F_fixed

Optional switches (they set the environment variables the code already reads):
    --prompt-mode compact|full     default compact
    --num-ctx 8192                 default 8192
    --temperature 0                default 0
    --no-json-mode                 turn JSON mode off
    --max-functions N              only review the first N functions

Nothing is written to the database (a stand-in session is used), so the
"analysis_runs" foreign-key error cannot happen. Accepted findings are saved
to findings.json instead.

Output folder: run_logs\<label>_<time>\
    full_log.txt    everything the pipeline printed
    llm_calls.json  per function: real prompt tokens, output tokens, response
    findings.json   findings that passed validation
    summary.txt     the table shown at the end
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--label", default="run")
    ap.add_argument("--prompt-mode", default="compact")
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--no-json-mode", action="store_true")
    ap.add_argument("--json-mode", action="store_true", help="accepted for compatibility (JSON mode is on by default)")
    ap.add_argument("--max-functions", type=int, default=None)
    return ap.parse_args()


class Tee:
    """Writes to the log file only (keeps the terminal quiet)."""

    def __init__(self, fh):
        self.fh = fh

    def write(self, s):
        self.fh.write(s)
        return len(s)

    def flush(self):
        self.fh.flush()


class FakeSession:
    """Stand-in for AsyncSessionLocal(): remembers findings, touches no database."""

    saved: list = []

    def __init__(self):
        self._pending = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def add(self, obj):
        self._pending.append(obj)

    async def commit(self):
        FakeSession.saved.extend(self._pending)
        self._pending = []


def main():
    args = parse_args()

    os.environ["LLM_PROVIDER"] = os.environ.get("LLM_PROVIDER", "ollama") or "ollama"
    os.environ["SEMANTIC_PROMPT_MODE"] = args.prompt_mode
    os.environ["OLLAMA_NUM_CTX"] = str(args.num_ctx)
    os.environ["OLLAMA_TEMPERATURE"] = str(args.temperature)
    os.environ["OLLAMA_JSON_MODE"] = "false" if args.no_json_mode else "true"

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("run_logs") / f"{args.label}_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_fh = open(out_dir / "full_log.txt", "w", encoding="utf-8")

    from app.services.llm_logic_reviewer import reviewer
    from app.services.llm_logic_reviewer import llm_provider as lp

    calls: list[dict] = []
    real_create = lp.create_llm_provider

    class LoggingProvider:
        def __init__(self, inner):
            self.inner = inner

        def generate(self, prompt, **kwargs):
            m = re.search(r"FUNCTION:\s*(\S+)", prompt)
            name = m.group(1) if m else "?"
            t0 = time.time()
            result = self.inner.generate(prompt, **kwargs)
            secs = time.time() - t0
            meta = result.get("meta") or {}
            text = result.get("response", "") or ""
            bug = None
            try:
                obj = json.loads(text)
                bug = obj.get("bug_found") if isinstance(obj, dict) else None
            except Exception:
                bug = "PARSE_FAIL"
            entry = {
                "n": len(calls) + 1,
                "function": name,
                "prompt_chars": len(prompt),
                "prompt_tokens": meta.get("prompt_tokens"),
                "output_tokens": meta.get("output_tokens"),
                "num_ctx": meta.get("num_ctx"),
                "prompt_truncated": meta.get("prompt_truncated"),
                "output_cut_off": meta.get("output_cut_off"),
                "seconds": round(secs, 1),
                "bug_found": bug,
                "error": result.get("error"),
                "response": text,
                "prompt": prompt,
            }
            calls.append(entry)
            flags = ""
            if entry["prompt_truncated"]:
                flags += "  !!PROMPT CUT"
            if entry["output_cut_off"]:
                flags += "  !!OUTPUT CUT"
            if entry["error"]:
                flags += f"  ERROR: {entry['error'][:80]}"
            sys.__stdout__.write(
                f"[{entry['n']:>2}] {name[:34]:<34} "
                f"prompt_tok={entry['prompt_tokens']} out_tok={entry['output_tokens']} "
                f"bug_found={bug} {entry['seconds']}s{flags}\n"
            )
            sys.__stdout__.flush()
            return result

    reviewer.create_llm_provider = lambda *a, **k: LoggingProvider(real_create(*a, **k))
    reviewer.AsyncSessionLocal = FakeSession

    print(f"Run folder : {out_dir}")
    print(f"Settings   : prompt={args.prompt_mode} num_ctx={args.num_ctx} temp={args.temperature} json={not args.no_json_mode}")
    print(f"Model      : {os.environ.get('OLLAMA_MODEL', 'qwen2.5-coder:3b-instruct-q4_K_M (default)')}")
    print("-" * 78)

    old_stdout = sys.stdout
    sys.stdout = Tee(log_fh)
    try:
        metrics = asyncio.run(
            reviewer.run_llm_logic_review(
                analysis_run_id="local-test",
                repository_path=args.repo,
                max_functions=args.max_functions,
            )
        )
    finally:
        sys.stdout = old_stdout
        log_fh.close()

    findings = []
    for issue in FakeSession.saved:
        findings.append(
            {
                "file": getattr(issue, "file_path", None),
                "line": getattr(issue, "line_number", None),
                "title": getattr(issue, "title", None),
                "description": getattr(issue, "description", None),
                "snippet": getattr(issue, "code_snippet", None),
            }
        )

    (out_dir / "llm_calls.json").write_text(json.dumps(calls, indent=2), encoding="utf-8")
    (out_dir / "findings.json").write_text(json.dumps(findings, indent=2), encoding="utf-8")

    lines = ["", "=" * 78, "RESULTS", "=" * 78]
    lines.append(f"LLM calls: {metrics.get('llm_calls_made')}   failures: {metrics.get('llm_failures')}   parse failures: {metrics.get('parse_failures')}")
    lines.append(f"LLM said bug: {metrics.get('findings_candidate')}   passed validation: {metrics.get('findings_validated')}   rejected: {metrics.get('findings_rejected')}")
    toks = [c["prompt_tokens"] for c in calls if isinstance(c["prompt_tokens"], int)]
    if toks:
        lines.append(f"Prompt tokens actually read: min {min(toks)}, max {max(toks)} (context {calls[0]['num_ctx']})")
    lines.append(f"Prompts cut: {sum(1 for c in calls if c['prompt_truncated'])}   outputs cut: {sum(1 for c in calls if c['output_cut_off'])}")
    lines.append("")
    lines.append("Findings that passed validation:")
    if findings:
        for f in findings:
            lines.append(f"  - {f['file']}:{f['line']}  {f['title']}")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append(f"Send me: {out_dir / 'full_log.txt'}  and  {out_dir / 'llm_calls.json'}")
    summary = "\n".join(lines)
    (out_dir / "summary.txt").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
