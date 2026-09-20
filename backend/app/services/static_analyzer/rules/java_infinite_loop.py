"""
JAVA_LOOP_001 — Infinite Loop Detection (Java)
-----------------------------------------------
Detects loops with constant true conditions (`while (true)`, `for (;;)`)
that have no reachable exit path (break, return, throw).

High-confidence detection criteria:
- Constant condition loops with no break/return/throw statements.
- Loops where all exit breaks are guarded by statically false conditions (`if (false) break;`).
- Loops where counter variables diverge away from the exit threshold (`int x = 0; while (true) { if (x > 10) break; x--; }`).

Suppression criteria (provably terminating / reachable):
- Unconditional `break`, `return`, `throw`, `System.exit()`.
- Conditional breaks with reachable dynamic conditions (`if (cond) break;`).
- Monotonically progressing counter variables that reach the exit threshold (`x++` towards `x >= 10`).
"""

from __future__ import annotations

from typing import Iterator, List, Optional

from ..analysis.loop_analyzer import LoopAnalyzer, LoopExitStatus
from ..base_rule import BaseRule
from ..models import CandidateIssue


class JavaInfiniteLoop(BaseRule):

    LANGUAGES = ["Java"]

    @property
    def rule_id(self) -> str:
        return "JAVA_LOOP_001"

    @property
    def issue_type(self) -> str:
        return "infinite_loop"

    @property
    def severity(self) -> str:
        return "high"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        for node in self._walk(ast):
            ntype = node.get("type", "")
            if ntype not in ("while_statement", "for_statement", "do_statement"):
                continue

            if not LoopAnalyzer.is_infinite_loop_candidate(node):
                continue

            status, explanation = LoopAnalyzer.analyze_loop_exits(node)

            if status in (LoopExitStatus.NO_EXIT, LoopExitStatus.UNREACHABLE_EXIT, LoopExitStatus.DIVERGING_COUNTER):
                self.record_syntax_match()
                yield self._make_issue(
                    node=node,
                    file_path=file_path,
                    source_lines=source_lines,
                    message=f"Infinite loop detected: loop condition is constantly true and {explanation.lower()}",
                    evidence={
                        "loop_type": ntype,
                        "exit_status": status.name.lower(),
                        "reason": explanation,
                        "confidence": "high",
                    },
                    confidence="high",
                )
            else:
                self.record_suppression(f"reachable_exit_{status.name.lower()}")
