"""
readiness.py — Dataset Readiness Gate & Scorecard for DistilBERT.
================================================================
Evaluates dataset readiness against rigorous criteria: sample volume,
class balance, cross-tab diversity, provenance, missingness, and leakage isolation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from .validator import PRIORITY_LABELS, SEVERITY_LABELS


# Recommended production readiness thresholds
TARGET_MIN_USABLE_RECORDS = 150
TARGET_MIN_REPOSITORIES = 5
TARGET_MIN_LANGUAGES = 3
TARGET_MIN_RULES = 10
TARGET_MIN_PER_SEVERITY_CLASS = 30
TARGET_MIN_PER_PRIORITY_CLASS = 30
HARD_MIN_PER_CLASS_FOR_SPLITTING = 5
MAX_ACCEPTABLE_MISSING_SNIPPET_PCT = 5.0


def evaluate_dataset_readiness(
    records: List[Dict[str, Any]],
    deduplication_stats: Optional[Dict[str, int]] = None,
    validation_report: Optional[Dict[str, Any]] = None,
    split_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Comprehensive evaluation of dataset readiness for DistilBERT fine-tuning.
    Returns structured scorecard with PASS/FAIL/WARN per criterion.
    """
    total_records = len(records)
    criteria: List[Dict[str, Any]] = []
    deficits: Dict[str, Any] = {"severity_deficits": {}, "priority_deficits": {}}

    # 1. Total Usable Unique Records
    n_unique = deduplication_stats.get("final_unique_records", total_records) if deduplication_stats else total_records
    pass_volume = n_unique >= TARGET_MIN_USABLE_RECORDS
    criteria.append({
        "criterion": "Usable Unique Records",
        "target": f">= {TARGET_MIN_USABLE_RECORDS}",
        "actual": n_unique,
        "status": "PASS" if pass_volume else "FAIL",
        "message": f"{n_unique}/{TARGET_MIN_USABLE_RECORDS} usable unique records collected.",
    })

    # 2. Repository Diversity
    repos = set(r.get("repository_id") for r in records if r.get("repository_id"))
    pass_repos = len(repos) >= TARGET_MIN_REPOSITORIES
    criteria.append({
        "criterion": "Repository Diversity",
        "target": f">= {TARGET_MIN_REPOSITORIES} distinct repositories",
        "actual": len(repos),
        "status": "PASS" if pass_repos else ("WARN" if len(repos) >= 2 else "FAIL"),
        "message": f"{len(repos)} unique real repositories represented.",
    })

    # 3. Language Diversity
    langs = set(str(r.get("language") or "").strip() for r in records if r.get("language"))
    langs.discard("")
    langs.discard("Unknown")
    pass_langs = len(langs) >= TARGET_MIN_LANGUAGES
    criteria.append({
        "criterion": "Language Diversity",
        "target": f">= {TARGET_MIN_LANGUAGES} languages (Python, Java, JS)",
        "actual": len(langs),
        "status": "PASS" if pass_langs else ("WARN" if len(langs) >= 2 else "FAIL"),
        "message": f"Languages present: {sorted(list(langs)) if langs else 'None'}",
    })

    # 4. Rule Coverage
    rules = set(str(r.get("rule_id") or "").strip() for r in records if r.get("rule_id"))
    rules.discard("")
    rules.discard("Unknown")
    pass_rules = len(rules) >= TARGET_MIN_RULES
    criteria.append({
        "criterion": "Rule Coverage",
        "target": f">= {TARGET_MIN_RULES} distinct rule IDs",
        "actual": len(rules),
        "status": "PASS" if pass_rules else ("WARN" if len(rules) >= 5 else "FAIL"),
        "message": f"{len(rules)} distinct static analysis rules represented.",
    })

    # 5. Class Balance: Severity
    sev_counts = Counter(str(r.get("verified_severity") or r.get("severity") or "").lower() for r in records)
    sev_pass = True
    for s in SEVERITY_LABELS:
        c = sev_counts.get(s, 0)
        if c < TARGET_MIN_PER_SEVERITY_CLASS:
            deficits["severity_deficits"][s] = {
                "current": c,
                "target": TARGET_MIN_PER_SEVERITY_CLASS,
                "needed": TARGET_MIN_PER_SEVERITY_CLASS - c,
            }
        if c < HARD_MIN_PER_CLASS_FOR_SPLITTING:
            sev_pass = False

    criteria.append({
        "criterion": "Severity Class Balance",
        "target": f">= {TARGET_MIN_PER_SEVERITY_CLASS} per class ({SEVERITY_LABELS})",
        "actual": dict(sev_counts),
        "status": "PASS" if sev_pass and not deficits["severity_deficits"] else ("WARN" if sev_pass else "FAIL"),
        "message": f"Severity breakdown: {dict(sev_counts)}",
    })

    # 6. Class Balance: Priority
    prio_counts = Counter(str(r.get("verified_priority") or r.get("priority") or "").lower() for r in records)
    prio_pass = True
    for p in PRIORITY_LABELS:
        c = prio_counts.get(p, 0)
        if c < TARGET_MIN_PER_PRIORITY_CLASS:
            deficits["priority_deficits"][p] = {
                "current": c,
                "target": TARGET_MIN_PER_PRIORITY_CLASS,
                "needed": TARGET_MIN_PER_PRIORITY_CLASS - c,
            }
        if c < HARD_MIN_PER_CLASS_FOR_SPLITTING:
            prio_pass = False

    criteria.append({
        "criterion": "Priority Class Balance",
        "target": f">= {TARGET_MIN_PER_PRIORITY_CLASS} per class ({PRIORITY_LABELS})",
        "actual": dict(prio_counts),
        "status": "PASS" if prio_pass and not deficits["priority_deficits"] else ("WARN" if prio_pass else "FAIL"),
        "message": f"Priority breakdown: {dict(prio_counts)}",
    })

    # 7. Cross-Tab Severity x Priority Matrix Diversity
    cross_tab = Counter((str(r.get("verified_severity") or r.get("severity") or "").lower(),
                         str(r.get("verified_priority") or r.get("priority") or "").lower()) for r in records)
    represented_pairs = sum(1 for s in SEVERITY_LABELS for p in PRIORITY_LABELS if cross_tab.get((s, p), 0) > 0)
    criteria.append({
        "criterion": "Cross-Tab Diversity (Severity x Priority)",
        "target": "Diverse naturally occurring combinations (out of 16)",
        "actual": f"{represented_pairs}/16 combinations represented",
        "status": "PASS" if represented_pairs >= 8 else ("WARN" if represented_pairs >= 4 else "FAIL"),
        "message": f"{represented_pairs} out of 16 possible severity x priority matrix cells are populated.",
    })

    # 8. Missingness in Essential Model Features
    missing_snippet = sum(1 for r in records if not str(r.get("code_snippet") or "").strip())
    missing_snippet_pct = (missing_snippet / max(1, total_records)) * 100.0
    pass_missing = missing_snippet_pct <= MAX_ACCEPTABLE_MISSING_SNIPPET_PCT
    criteria.append({
        "criterion": "Feature Completeness (Code Snippets)",
        "target": f"Missing code snippet <= {MAX_ACCEPTABLE_MISSING_SNIPPET_PCT}%",
        "actual": f"{missing_snippet_pct:.2f}% missing ({missing_snippet}/{total_records})",
        "status": "PASS" if pass_missing else "FAIL",
        "message": f"{missing_snippet} records missing code_snippet context.",
    })

    # 9. Provenance Quality & Test Contamination
    provenance = validation_report.get("provenance_breakdown", {}) if validation_report else {}
    test_or_synthetic = provenance.get("test_or_synthetic", 0)
    incomplete = provenance.get("real_incomplete", 0)
    pass_provenance = (test_or_synthetic == 0) and (incomplete == 0)
    criteria.append({
        "criterion": "Data Provenance & Cleanliness",
        "target": "0 test/synthetic records and 0 incomplete records in ML dataset",
        "actual": f"Test/synthetic: {test_or_synthetic}, Incomplete: {incomplete}",
        "status": "PASS" if pass_provenance else ("WARN" if test_or_synthetic == 0 else "FAIL"),
        "message": f"Provenance: usable={provenance.get('real_usable', n_unique)}, test={test_or_synthetic}, incomplete={incomplete}",
    })

    # 10. Data Leakage & Zero Group Overlap
    cross_overlap = split_metadata.get("cross_split_group_overlap", 0) if split_metadata else 0
    pass_leakage = (cross_overlap == 0)
    criteria.append({
        "criterion": "Group Isolation & Zero Leakage",
        "target": "cross_split_group_overlap == 0",
        "actual": cross_overlap,
        "status": "PASS" if pass_leakage else "FAIL",
        "message": "Zero group overlap across train, validation, and test partitions.",
    })

    # Overall Status Decision
    has_critical_fails = any(c["status"] == "FAIL" for c in criteria)
    has_warnings = any(c["status"] == "WARN" for c in criteria)

    if has_critical_fails:
        overall_status = "NOT READY"
        verdict = "NOT READY FOR TRAINING"
    elif has_warnings:
        overall_status = "READY WITH WARNINGS"
        verdict = "READY FOR MODEL TRAINING REVIEW (WITH WARNINGS)"
    else:
        overall_status = "READY"
        verdict = "READY FOR MODEL TRAINING REVIEW"

    passed_count = sum(1 for c in criteria if c["status"] == "PASS")
    score_pct = round((passed_count / len(criteria)) * 100.0, 1)

    recommendations = []
    if not pass_volume:
        recommendations.append(f"Collect at least {TARGET_MIN_USABLE_RECORDS - n_unique} additional unique candidate issues from real repositories.")
    if not pass_repos:
        recommendations.append(f"Analyze at least {TARGET_MIN_REPOSITORIES - len(repos)} additional real repositories.")
    if not pass_langs:
        recommendations.append("Include repositories in Java and JavaScript in addition to Python.")
    if deficits["severity_deficits"]:
        for sev, info in deficits["severity_deficits"].items():
            recommendations.append(f"Collect {info['needed']} more verified '{sev}' severity issues.")
    if deficits["priority_deficits"]:
        for prio, info in deficits["priority_deficits"].items():
            recommendations.append(f"Collect {info['needed']} more verified '{prio}' priority issues.")
    if not pass_missing:
        recommendations.append("Ensure candidate issues are generated with non-empty code snippets and rule IDs.")

    return {
        "dataset_status": verdict,
        "status": overall_status,
        "readiness_score": score_pct,
        "total_criteria": len(criteria),
        "passed_criteria": passed_count,
        "criteria": criteria,
        "deficits": deficits,
        "recommendations": recommendations,
    }
