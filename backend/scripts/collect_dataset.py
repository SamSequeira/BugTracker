"""
collect_dataset.py — Developer Tool for Real Repository Ingestion, Analysis & Review.
=====================================================================================
Streamlines ingesting real Python, Java, and JavaScript repositories (local folders or Git URLs),
generating candidate issues with Tree-sitter AST, persisting them in PostgreSQL,
sampling deterministic review batches, interactive human-in-the-loop review,
inspecting the review queue, and evaluating readiness.

Usage:
  python scripts/collect_dataset.py --status
  python scripts/collect_dataset.py --sample-batch --size 200 --seed 42
  python scripts/collect_dataset.py --export-batch data/review_batch_200.json
  python scripts/collect_dataset.py --review --size 200
  python scripts/collect_dataset.py --queue --limit 20
  python scripts/collect_dataset.py --path "C:/path/to/repo" --name "my-project"
  python scripts/collect_dataset.py --git "https://github.com/owner/repo.git" --name "my-project"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
from dotenv import load_dotenv
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Setup path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

load_dotenv(backend_dir / ".env")

from app.models.analysis_run import AnalysisRun
from app.models.candidate_issues import CandidateIssue
from app.models.repository import Repository
from app.repositories.candidate_issue_repo import candidate_issue_repository
from app.services.ast_generator import ast_generator
from app.services.candidate_issue_service import candidate_issue_service
from app.services.dataset_preparation import ReviewSampler, dataset_preparation_service
from app.services.repository_analysis_service import repository_analysis_service


def get_db_url() -> str:
    db_url = os.environ.get("POSTGRES_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if not db_url:
        db_url = "sqlite+aiosqlite:///:memory:"
    return db_url


from app.services.source_context import get_source_context


async def get_batch_progress(session: AsyncSession, item_ids: list[str]) -> dict:
    """
    Query live PostgreSQL database to compute status of sampled review batch items.
    """
    if not item_ids:
        return {
            "total": 0,
            "confirmed_valid": 0,
            "false_positives": 0,
            "unreviewed": 0,
            "partially_labeled": 0,
            "remaining": 0,
            "item_statuses": {},
        }

    stmt = select(CandidateIssue).where(CandidateIssue.id.in_(item_ids))
    result = await session.execute(stmt)
    issues = {iss.id: iss for iss in result.scalars().all()}

    confirmed = 0
    false_positives = 0
    unreviewed = 0
    partially_labeled = 0

    item_statuses = {}
    for i_id in item_ids:
        iss = issues.get(i_id)
        if not iss:
            status_str = "MISSING"
            unreviewed += 1
        elif iss.verified_severity is not None and iss.verified_priority is not None:
            status_str = "CONFIRMED_VALID"
            confirmed += 1
        elif iss.verified_at is not None and (
            (iss.verification_notes and iss.verification_notes.startswith("[FALSE_POSITIVE]"))
            or (iss.verified_severity is None and iss.verified_priority is None)
        ):
            status_str = "FALSE_POSITIVE"
            false_positives += 1
        elif (iss.verified_severity is not None and iss.verified_priority is None) or (
            iss.verified_severity is None and iss.verified_priority is not None
        ):
            status_str = "PARTIALLY_LABELED"
            partially_labeled += 1
        else:
            status_str = "UNREVIEWED"
            unreviewed += 1
        item_statuses[i_id] = status_str

    remaining = unreviewed + partially_labeled
    return {
        "total": len(item_ids),
        "confirmed_valid": confirmed,
        "false_positives": false_positives,
        "unreviewed": unreviewed,
        "partially_labeled": partially_labeled,
        "remaining": remaining,
        "item_statuses": item_statuses,
    }


async def print_status(session: AsyncSession):
    """Print current dataset statistics, class balances, 4x4 matrix, and readiness scorecard."""
    print("=" * 75)
    print("                 DATASET COLLECTION & READINESS STATUS")
    print("=" * 75)

    stats = await candidate_issue_repository.get_dataset_stats(session)
    readiness_data = await dataset_preparation_service.evaluate_readiness(session)
    readiness = readiness_data["readiness"]

    print(f"Total Candidate Issues in DB:     {stats['total_candidate_issues']}")
    print(f"  - Completely Unverified:         {stats['unverified']}")
    print(f"  - False Positives (Excluded):    {stats.get('false_positives', 0)}")
    print(f"  - Partially Verified:           {stats['partially_verified']}")
    print(f"  - Fully Verified:               {stats['fully_verified']}")

    print("\nVerified Severity Class Balance (Target: >= 30 per class):")
    for sev, count in stats["severity_distribution"].items():
        status_tag = "[MET]" if count >= 30 else f"[{count}/30]"
        print(f"  - {sev:<10}: {count:>3}  {status_tag}")

    print("\nVerified Priority Class Balance (Target: >= 30 per class):")
    for prio, count in stats["priority_distribution"].items():
        status_tag = "[MET]" if count >= 30 else f"[{count}/30]"
        print(f"  - {prio:<10}: {count:>3}  {status_tag}")

    print("\nVerified Severity x Priority 3x3 Cross-Tab (Real Ground Truth):")
    crosstab = stats.get("crosstab", {})
    severities = ["high", "medium", "low"]
    priorities = ["p1", "p2", "p3"]
    header = "           " + "  ".join(f"{p.upper():>6}" for p in priorities)
    print(header)
    print("  " + "-" * len(header))
    for s in severities:
        row = f"  {s.capitalize():<8} |"
        for p in priorities:
            key = f"{s} + {p}"
            count = crosstab.get(key, 0)
            row += f" {count:>6}"
        print(row)

    diversity = stats.get("diversity_counts", {})
    print(f"\nData Diversity (Verified Records):")
    print(f"  - Unique Rules:          {diversity.get('unique_rules', 0)}")
    print(f"  - Unique Languages:      {diversity.get('unique_languages', 0)}")
    print(f"  - Unique File Paths:     {diversity.get('unique_file_paths', 0)}")
    print(f"  - Unique Code Snippets:  {diversity.get('unique_code_snippets', 0)}")
    print(f"  - Unique Repositories:   {diversity.get('unique_repositories', 0)}")

    print("-" * 75)
    print(f"READINESS SCORECARD: {readiness['dataset_status']} ({readiness['readiness_score']}% Score)")
    print("-" * 75)
    for c in readiness["criteria"]:
        icon = "[PASS]" if c["status"] == "PASS" else ("[WARN]" if c["status"] == "WARN" else "[FAIL]")
        print(f"  {icon:<7} {c['criterion']:<35} : {c['message']}")

    if readiness["recommendations"]:
        print("\nACTIONABLE RECOMMENDATIONS:")
        for idx, rec in enumerate(readiness["recommendations"], 1):
            print(f"  {idx}. {rec}")
    print("=" * 75)


async def sample_review_batch(
    session: AsyncSession,
    target_size: int = 200,
    random_seed: int = 42,
    export_path: str | None = None,
) -> tuple[list[dict], dict]:
    """Sample a deterministic review batch and print the distribution report."""
    print("=" * 75)
    print(f"       DETERMINISTIC REVIEW BATCH SAMPLING (Target Size: {target_size}, Seed: {random_seed})")
    print("=" * 75)

    all_unverified = await candidate_issue_repository.get_all_unverified_issues_with_repo(session)
    sampler = ReviewSampler(random_seed=random_seed)
    sampled_items, report = sampler.sample(
        records=all_unverified,
        target_size=target_size,
    )

    print(f"Total Available Real Unverified Issues : {report['total_available_unverified_real']}")
    print(f"Sampled Review Batch Size              : {report['sampled_count']}")
    print(f"Distinct Strata Represented            : {report['strata_count']}")

    print("\nRepositories Represented:")
    for repo, count in sorted(report["repositories_distribution"].items(), key=lambda x: -x[1]):
        print(f"  - {repo:<30}: {count} candidates")

    print("\nLanguages Represented:")
    for lang, count in sorted(report["languages_distribution"].items(), key=lambda x: -x[1]):
        print(f"  - {lang:<30}: {count} candidates")

    print("\nRules Represented (12/12 Targeted):")
    for rule, count in sorted(report["rules_distribution"].items(), key=lambda x: -x[1]):
        print(f"  - {rule:<30}: {count} candidates")

    print("\nIssue Types Represented:")
    for itype, count in sorted(report["issue_types_distribution"].items(), key=lambda x: -x[1]):
        print(f"  - {itype:<30}: {count} candidates")

    if export_path:
        out_p = Path(export_path)
        if not out_p.is_absolute():
            out_p = backend_dir / export_path
        out_p.parent.mkdir(parents=True, exist_ok=True)
        export_payload = {
            "metadata": report,
            "items": [
                {
                    "id": item["id"],
                    "repository_name": item.get("repository_name", ""),
                    "repository_id": item.get("repository_id", ""),
                    "analysis_run_id": item.get("analysis_run_id", ""),
                    "language": item.get("language", ""),
                    "rule_id": item.get("rule_id", ""),
                    "issue_type": item.get("issue_type", ""),
                    "file_path": item.get("file_path", ""),
                    "line_number": item.get("line_number"),
                    "code_snippet": item.get("code_snippet", ""),
                    "message": item.get("message", ""),
                    "evidence": item.get("evidence", {}),
                    "detector_severity": item.get("severity", ""),
                    "detector_urgency": item.get("urgency", ""),
                }
                for item in sampled_items
            ],
        }
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(export_payload, f, indent=2)
        print(f"\nSuccessfully exported {len(sampled_items)} review batch items to: {out_p}")

    print("=" * 75)
    return sampled_items, report


async def interactive_review_session(
    session: AsyncSession,
    target_size: int = 200,
    random_seed: int = 42,
    resume: bool = True,
    hide_detector_labels: bool = False,
    batch_file: str | None = None,
):
    """
    Comprehensive interactive human-in-the-loop CLI review session.
    Supports confirmation, false positive marking, skipping, back navigation,
    source context inspection, progress monitoring, and session resumption.
    """
    batch_path = Path(batch_file) if batch_file else backend_dir / "data" / f"review_batch_{target_size}.json"
    sampled_items = []
    report = {}

    # 1. Load batch from file if exists or generate deterministically
    if batch_path.exists():
        try:
            with open(batch_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                sampled_items = data.get("items", [])
                report = data.get("metadata", {})
            print(f"Loaded existing deterministic review batch ({len(sampled_items)} items) from: {batch_path}")
        except Exception as e:
            print(f"Could not load {batch_path}: {e}. Sampling from database...")

    if not sampled_items:
        sampled_items, report = await sample_review_batch(
            session, target_size=target_size, random_seed=random_seed, export_path=str(batch_path)
        )

    if not sampled_items:
        print("No candidate issues available for review.")
        return

    item_ids = [item["id"] for item in sampled_items]
    batch_progress = await get_batch_progress(session, item_ids)

    print("\n" + "=" * 75)
    print("                 HUMAN GROUND-TRUTH REVIEW SESSION")
    print("=" * 75)
    print(f"Review Batch Size   : {batch_progress['total']}")
    print(f"Confirmed Valid     : {batch_progress['confirmed_valid']}")
    print(f"False Positives     : {batch_progress['false_positives']}")
    print(f"Partially Labeled   : {batch_progress['partially_labeled']}")
    print(f"Unreviewed/Skipped  : {batch_progress['unreviewed']}")
    print(f"Remaining to Review : {batch_progress['remaining']}")
    if hide_detector_labels:
        print("[Blinded Mode] Detector baseline predictions are hidden to reduce anchoring bias.")
    print("=" * 75)

    # 2. Determine starting index (resume at first unreviewed/partial item)
    start_idx = 0
    if resume and batch_progress["remaining"] > 0:
        for idx, item in enumerate(sampled_items):
            status_str = batch_progress["item_statuses"].get(item["id"], "UNREVIEWED")
            if status_str in ("UNREVIEWED", "PARTIALLY_LABELED"):
                start_idx = idx
                break

    print(f"Starting review at Issue [{start_idx + 1}/{len(sampled_items)}]...\n")
    print("Available Commands:")
    print("  [c] Confirm valid issue (input verified severity, priority, notes)")
    print("  [f] Mark false positive (input technical explanation)")
    print("  [s] Skip / Next issue")
    print("  [b] Go back to previous issue")
    print("  [v] View full source code context around line")
    print("  [r] Show repository & file metadata")
    print("  [p] Show dataset progress dashboard")
    print("  [q] Quit and save progress\n")

    curr_idx = start_idx
    session_confirmed = 0
    session_fp = 0
    session_skipped = 0

    while curr_idx < len(sampled_items):
        item = sampled_items[curr_idx]
        issue_id = item["id"]

        # Fetch latest state from DB
        live_issue = await candidate_issue_repository.get_by_id(session, issue_id)
        if live_issue:
            if live_issue.verified_severity and live_issue.verified_priority:
                current_status = f"CONFIRMED_VALID (severity={live_issue.verified_severity}, priority={live_issue.verified_priority})"
            elif live_issue.verified_at and (live_issue.verification_notes and live_issue.verification_notes.startswith("[FALSE_POSITIVE]")):
                current_status = "FALSE_POSITIVE"
            elif live_issue.verified_severity or live_issue.verified_priority:
                current_status = f"PARTIALLY_LABELED (severity={live_issue.verified_severity}, priority={live_issue.verified_priority})"
            else:
                current_status = "UNREVIEWED"
        else:
            current_status = "UNREVIEWED"

        print("=" * 75)
        print(f"ISSUE {curr_idx + 1} / {len(sampled_items)}  [ID: {issue_id}]")
        print(f"  Repository:   {item.get('repository_name', 'N/A')} ({item.get('language', 'N/A')})")
        print(f"  Analysis Run: {item.get('analysis_run_id', 'N/A')}")
        print(f"  Rule ID:      {item.get('rule_id', 'N/A')}")
        print(f"  Issue Type:   {item.get('issue_type', 'N/A')}")
        print(f"  File:         {item.get('file_path', 'N/A')}")
        print(f"  Line:         {item.get('line_number', 'N/A')}")
        print(f"  Message:      {item.get('message', 'N/A')}")
        if item.get("description"):
            print(f"  Description:  {item['description']}")

        if item.get("code_snippet"):
            print(f"\n  Code Snippet:")
            for line in item["code_snippet"].strip().splitlines()[:10]:
                print(f"    | {line}")

        if item.get("evidence"):
            print(f"\n  AST Evidence: {item['evidence']}")

        if not hide_detector_labels:
            print(f"\n  [Detector Baseline Prediction] (Reference only):")
            print(f"    Severity:   {item.get('detector_severity') or item.get('severity', 'N/A')}")
            print(f"    Urgency:    {item.get('detector_urgency') or item.get('urgency', 'N/A')}")

        print(f"\n  Human Review Status: {current_status}")
        print("=" * 75)

        action = input("Action [c=Confirm, f=False Positive, s=Skip, b=Back, v=Context, r=Metadata, p=Progress, q=Quit]: ").strip().lower()

        if action == "q":
            print("\nSaving review session and exiting...")
            break
        elif action == "b":
            if curr_idx > 0:
                curr_idx -= 1
                print(f"\n<- Stepped back to Issue {curr_idx + 1}")
            else:
                print("\nAlready at the first issue in the review batch.")
            continue
        elif action == "v":
            file_p = item.get("file_path", "")
            line_no = item.get("line_number")
            ok, ctx_text = get_source_context(file_p, line_no, context_lines=15)
            print("\n" + ctx_text + "\n")
            continue
        elif action == "r":
            print("\n" + "-" * 60)
            print("REPOSITORY & CANDIDATE ISSUE METADATA:")
            print(f"  Issue ID:        {issue_id}")
            print(f"  Repository Name: {item.get('repository_name')}")
            print(f"  Repository ID:   {item.get('repository_id')}")
            print(f"  Analysis Run ID: {item.get('analysis_run_id')}")
            print(f"  File Path:       {item.get('file_path')}")
            print(f"  Line Number:     {item.get('line_number')}")
            print(f"  Language:        {item.get('language')}")
            print(f"  Rule ID:         {item.get('rule_id')}")
            print(f"  Issue Type:      {item.get('issue_type')}")
            print(f"  Raw Evidence:    {json.dumps(item.get('evidence', {}), indent=2)}")
            print("-" * 60 + "\n")
            continue
        elif action == "p":
            print("\n")
            curr_progress = await get_batch_progress(session, item_ids)
            print(f"Batch Progress: {curr_progress['confirmed_valid']} Confirmed, {curr_progress['false_positives']} False Positives, {curr_progress['partially_labeled']} Partial, {curr_progress['unreviewed']} Unreviewed.")
            await print_status(session)
            continue
        elif action == "f":
            while True:
                notes = input("False Positive Technical Explanation (required): ").strip()
                if notes:
                    break
                print("Error: Technical explanation is required when marking a false positive.")

            await candidate_issue_repository.update_labels(
                db=session,
                issue_id=issue_id,
                is_false_positive=True,
                verification_notes=notes,
            )
            session_fp += 1
            print(f"  [OK] Marked issue {issue_id} as FALSE POSITIVE.")
            curr_idx += 1
        elif action == "c":
            # 1. Ask for severity
            while True:
                sev_input = input("Verified Severity [high / medium / low]: ").strip().lower()
                if sev_input in ("high", "medium", "low"):
                    break
                print("Error: Invalid severity. Must be one of: high, medium, low")

            # 2. Ask for priority
            while True:
                prio_input = input("Verified Priority [p1 / p2 / p3]: ").strip().lower()
                if prio_input in ("p1", "p2", "p3"):
                    break
                print("Error: Invalid priority. Must be one of: p1, p2, p3")

            # 3. Ask for reviewer rationale
            while True:
                notes = input("Reviewer Verification Rationale (required): ").strip()
                if notes:
                    break
                print("Error: Rationale cannot be empty.")

            # Apply label update to live PostgreSQL DB
            await candidate_issue_repository.update_labels(
                db=session,
                issue_id=issue_id,
                verified_severity=sev_input,
                verified_priority=prio_input,
                verification_notes=notes,
                is_false_positive=False,
            )
            await session.commit()
            session_confirmed += 1
            print(f"  [OK] Successfully labeled issue {issue_id}: {sev_input.upper()} / {prio_input.upper()}")
            curr_idx += 1
        elif action == "s":
            session_skipped += 1
            print(f"  [>] Skipped issue {issue_id} (remains in review queue).")
            curr_idx += 1
        else:
            print("Unrecognized command. Enter c, f, s, b, v, r, p, or q.")
            continue

    print("\n" + "=" * 75)
    print("                   REVIEW SESSION SUMMARY")
    print("=" * 75)
    print(f"  Issues Confirmed in this Session : {session_confirmed}")
    print(f"  False Positives Recorded          : {session_fp}")
    print(f"  Issues Skipped                   : {session_skipped}")
    final_progress = await get_batch_progress(session, item_ids)
    print(f"\n  Total Batch Progress:")
    print(f"    - Confirmed Valid   : {final_progress['confirmed_valid']} / {final_progress['total']}")
    print(f"    - False Positives   : {final_progress['false_positives']} / {final_progress['total']}")
    print(f"    - Partially Labeled : {final_progress['partially_labeled']} / {final_progress['total']}")
    print(f"    - Remaining to Review: {final_progress['remaining']} / {final_progress['total']}")
    print("=" * 75)
    await print_status(session)


async def print_queue(session: AsyncSession, limit: int = 15):
    """Print top unverified issues waiting for manual review."""
    print("=" * 75)
    print(f"            MANUAL LABELLING REVIEW QUEUE (Top {limit})")
    print("=" * 75)

    items, total = await candidate_issue_repository.list_issues(
        session, verification_status="unverified", limit=limit
    )

    if not items:
        print("No unverified candidate issues currently in the review queue.")
        return

    for idx, iss in enumerate(items, 1):
        print(f"\n[{idx}/{total}] Issue ID: {iss.id}")
        print(f"  Rule ID:     {iss.rule_id or 'N/A'}")
        print(f"  Issue Type:  {iss.issue_type or 'N/A'}")
        print(f"  Language:    {iss.language or 'N/A'}")
        print(f"  Location:    {iss.file_path}:{iss.line_number}")
        print(f"  Detector:    severity={iss.severity}, urgency={iss.urgency}")
        print(f"  Message:     {iss.message}")
        if iss.code_snippet:
            print(f"  Snippet:")
            for line in iss.code_snippet.strip().splitlines()[:6]:
                print(f"    | {line}")
        print(f"  PATCH API:   PATCH /candidate-issues/{iss.id}/labels")
        print(f"               {{\"verified_severity\": \"critical|high|medium|low\", \"verified_priority\": \"p1|p2|p3|p4\", \"verification_notes\": \"...\"}}")
    print("=" * 75)


async def analyze_repo_folder(
    session: AsyncSession,
    repo_path: str | Path,
    repo_name: str | None = None,
    source_url: str | None = None,
) -> dict:
    """Analyze a local repository directory and store candidate issues."""
    target_dir = Path(repo_path).resolve()
    if not target_dir.exists() or not target_dir.is_dir():
        raise FileNotFoundError(f"Directory '{target_dir}' does not exist or is not a directory.")

    name = repo_name or target_dir.name
    print(f"\n{'='*75}")
    print(f"Analyzing repository: '{name}'")
    print(f"Source path: {target_dir}")
    print(f"{'='*75}")

    # 1. Create Repository in DB
    repo = Repository(
        id=str(uuid.uuid4()),
        name=name,
        s3_key=source_url or f"repositories/{name}.zip",
    )
    session.add(repo)
    await session.flush()

    # 2. Create AnalysisRun in DB
    run = AnalysisRun(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        status="running",
    )
    session.add(run)
    await session.flush()

    # 3. Generate AST and Candidate Issues
    print("Generating AST across multi-language source trees...")
    ast_result = ast_generator.generate_ast_for_repository(str(target_dir))
    print(f"AST Completed: {ast_result.get('total_files', 0)} total files ({ast_result.get('supported_files', 0)} supported source files)")

    print("Running Static Analysis Rules...")
    candidate_result = candidate_issue_service.generate_from_repository(ast_result)
    raw_issues = candidate_result.get("candidate_issues", [])
    print(f"Candidate Issues Found: {len(raw_issues)}")

    # 4. Persist to PostgreSQL
    analysis_payload = {
        "total_files": ast_result.get("total_files", 0),
        "supported_files": ast_result.get("supported_files", 0),
        "candidate_issues": raw_issues,
    }
    completed_run = await repository_analysis_service.complete_analysis_run(
        session, run.id, analysis_payload
    )
    await session.commit()

    # Summarize findings
    rules_triggered = {}
    severities = {}
    snippets_count = 0
    evidence_count = 0

    for iss in raw_issues:
        r_id = iss.get("rule_id", "UNKNOWN")
        rules_triggered[r_id] = rules_triggered.get(r_id, 0) + 1
        sev = iss.get("severity", "medium")
        severities[sev] = severities.get(sev, 0) + 1
        if iss.get("code_snippet"):
            snippets_count += 1
        if iss.get("evidence"):
            evidence_count += 1

    summary = {
        "repository_id": repo.id,
        "repository_name": name,
        "analysis_run_id": completed_run.id,
        "total_files": ast_result.get("total_files", 0),
        "supported_files": ast_result.get("supported_files", 0),
        "candidate_issues_count": len(raw_issues),
        "rules_triggered": rules_triggered,
        "detector_severities": severities,
        "snippets_count": snippets_count,
        "evidence_count": evidence_count,
    }

    print(f"\nAnalysis Completed Successfully!")
    print(f"  Repository ID:    {repo.id}")
    print(f"  Analysis Run ID:  {completed_run.id}")
    print(f"  Supported Files:  {summary['supported_files']}")
    print(f"  Issues Stored:    {summary['candidate_issues_count']}")
    print(f"  With Snippets:    {summary['snippets_count']}")
    print(f"  With Evidence:    {summary['evidence_count']}")
    print("  Rules Triggered:")
    for r, c in rules_triggered.items():
        print(f"    - {r:<25}: {c}")

    return summary


async def clone_and_analyze_git(
    session: AsyncSession,
    git_url: str,
    repo_name: str | None = None,
) -> dict:
    """Clone a public Git repository shallowly and analyze it."""
    name = repo_name or git_url.rstrip("/").split("/")[-1].replace(".git", "")
    temp_dir = Path(tempfile.mkdtemp(prefix=f"repo_{name}_"))

    print(f"\nCloning Git repository: {git_url} into {temp_dir}...")
    try:
        cmd = ["git", "clone", "--depth", "1", git_url, str(temp_dir)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(f"Git clone failed: {proc.stderr}")
        print("Clone completed.")

        summary = await analyze_repo_folder(session, temp_dir, name, source_url=git_url)
        return summary
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def main():
    parser = argparse.ArgumentParser(description="BugTracker Dataset Collection & Review CLI")
    parser.add_argument("--status", action="store_true", help="Print current dataset collection & readiness status")
    parser.add_argument("--queue", action="store_true", help="Print unverified candidate issues review queue")
    parser.add_argument("--limit", type=int, default=15, help="Max queue items to display")
    parser.add_argument("--path", type=str, default=None, help="Local path to repository folder for static analysis")
    parser.add_argument("--git", type=str, default=None, help="Git clone URL to clone and analyze")
    parser.add_argument("--name", type=str, default=None, help="Name for repository")
    parser.add_argument("--sample-batch", action="store_true", help="Sample a deterministic balanced review batch")
    parser.add_argument("--size", type=int, default=200, help="Target review batch size (default: 200)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for deterministic sampling (default: 42)")
    parser.add_argument("--export-batch", type=str, default=None, help="File path to export review batch as JSON")
    parser.add_argument("--review", action="store_true", help="Start interactive human review CLI session")
    parser.add_argument("--hide-detector-labels", action="store_true", help="Suppress detector baseline predictions during labeling to reduce anchoring bias")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True, help="Resume review session at first unreviewed item (default: True)")
    parser.add_argument("--batch-file", type=str, default=None, help="Path to pre-existing review batch JSON file")

    args = parser.parse_args()

    engine = create_async_engine(get_db_url(), echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        if args.sample_batch or args.export_batch:
            await sample_review_batch(session, target_size=args.size, random_seed=args.seed, export_path=args.export_batch)
        elif args.review:
            await interactive_review_session(
                session,
                target_size=args.size,
                random_seed=args.seed,
                resume=args.resume,
                hide_detector_labels=args.hide_detector_labels,
                batch_file=args.batch_file,
            )
        elif args.git:
            await clone_and_analyze_git(session, args.git, args.name)
        elif args.path:
            await analyze_repo_folder(session, args.path, args.name)
        elif args.queue:
            await print_queue(session, args.limit)
        else:
            await print_status(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
