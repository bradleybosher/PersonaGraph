"""
Option 3: Adversarial answer test.

Drives a session with deliberately bad answers and checks:
  - All evaluation scores ≤ 5
  - At least one answer has a non-empty gaps array
  - Judge fires verdict="flag" at least once
  - Interview eventually completes (end_interview or questions exhausted)

Usage:
    cd scripts && uv run python adversarial_test.py
"""
import asyncio
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)   # for headless_runner

from headless_runner import run_session

BAD_ANSWERS = [
    "It depends on the situation. I just try to do my best in each context.",
    "I leverage synergies across stakeholders and utilise agile frameworks to drive alignment and unlock value.",
    "I never delegate. Actually, I do delegate everything. It really depends on the team.",
    "I think AI is really important and we should definitely use it more strategically going forward.",
    "I've worked with many customers and I always put them first by focusing on their individual needs.",
]


def _run_checks(final_state: dict) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    answers = final_state.get("answers", [])

    # Check 1: all scores ≤ 5
    scores = [r["evaluation"].get("score", 10) for r in answers if r.get("evaluation")]
    all_low = bool(scores) and all(s <= 5 for s in scores)
    checks.append(("All scores ≤ 5", all_low, f"scores={scores}"))

    # Check 2: at least one non-empty gaps array
    has_gaps = any(
        len(r["evaluation"].get("gaps", [])) > 0
        for r in answers if r.get("evaluation")
    )
    checks.append(("At least one answer has gaps identified", has_gaps, ""))

    # Check 3: judge flagged at least one evaluation
    n_flags = sum(
        1 for r in answers
        if r.get("judge_verdict") and r["judge_verdict"].get("verdict") == "flag"
    )
    checks.append(("Judge fired 'flag' at least once", n_flags > 0, f"flags={n_flags}"))

    # Check 4: session completed
    completed = bool(final_state.get("interview_complete") or final_state.get("debrief"))
    checks.append(("Interview completed", completed, ""))

    return checks


def main() -> int:
    print("\nAdversarial Answer Test — deliberately bad answers")
    print("=" * 60)
    final_state, _ = asyncio.run(run_session(BAD_ANSWERS, model_tier="sonnet"))

    print("\nEvaluation scores per turn:")
    for i, rec in enumerate(final_state.get("answers", []), 1):
        ev = rec.get("evaluation") or {}
        verdict = rec.get("judge_verdict") or {}
        print(
            f"  Turn {i}: score={ev.get('score', '?')}/10  "
            f"gaps={ev.get('gaps', [])}  "
            f"judge={verdict.get('verdict', 'none')}"
        )

    print("\nCHECKS:")
    checks = _run_checks(final_state)
    all_passed = True
    for label, passed, detail in checks:
        status = "PASS" if passed else "FAIL"
        suffix = f"  [{detail}]" if detail else ""
        print(f"  {status}: {label}{suffix}")
        if not passed:
            all_passed = False

    print()
    print("RESULT:", "ALL PASS" if all_passed else "SOME CHECKS FAILED")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
