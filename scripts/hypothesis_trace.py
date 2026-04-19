"""
Option 2: Hypothesis coherence check.

Drives a 5-turn session with answers that escalate in quality and prints
hypothesis evolution turn by turn. Checks:
  - Confidence increases for at least one competency across the session
  - No competency stays "unknown" past turn 3
  - No settled competency (confidence > 0.5) regresses by more than 0.2

Usage:
    cd scripts && uv run python hypothesis_trace.py
"""
import asyncio
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)   # for headless_runner

from headless_runner import run_session

ANSWERS = [
    "I'm not sure, I just try to figure it out as I go.",
    "I usually involve the team and try to think about what the customer needs.",
    "I use structured frameworks like DACI and always tie decisions back to measurable outcomes.",
    "I've built agentic pipelines using LangGraph and the Anthropic SDK — tool use, extended thinking, prompt caching.",
    "I led a team of 8 SAs across EMEA, grew pipeline by 60% and reduced time-to-first-value from 6 weeks to 2.",
]

_COMPETENCIES = [
    "leadership",
    "technical_depth",
    "agentic_systems",
    "customer_empathy",
    "strategic_thinking",
]


def _print_table(snapshots: list[dict]) -> None:
    header = f"  {'Turn':>4}  {'Competency':<22}  {'Signal':<10}  {'Confidence':>10}"
    sep = "  " + "-" * 53
    print(header)
    print(sep)
    for snap in snapshots:
        turn = snap["turn"]
        for comp in _COMPETENCIES:
            h = snap["hypotheses"].get(comp, {})
            print(
                f"  {turn:>4}  {comp:<22}  {h.get('signal', '?'):<10}  "
                f"{h.get('confidence', 0.0):>10.2f}"
            )
        print()


def _check_coherence(snapshots: list[dict]) -> list[str]:
    failures = []

    if len(snapshots) >= 3:
        turn3 = snapshots[2]["hypotheses"]
        for comp, h in turn3.items():
            if h["signal"] == "unknown":
                failures.append(f"{comp} still 'unknown' at turn 3")

    if len(snapshots) >= 2:
        first = snapshots[0]["hypotheses"]
        last = snapshots[-1]["hypotheses"]
        any_improved = any(
            last.get(c, {}).get("confidence", 0) > first.get(c, {}).get("confidence", 0)
            for c in _COMPETENCIES
        )
        if not any_improved:
            failures.append("No competency confidence increased across the session")

    for i in range(1, len(snapshots)):
        for comp in _COMPETENCIES:
            prev = snapshots[i - 1]["hypotheses"].get(comp, {}).get("confidence", 0)
            curr = snapshots[i]["hypotheses"].get(comp, {}).get("confidence", 0)
            if prev > 0.5 and curr < prev - 0.2:
                failures.append(
                    f"{comp} regressed from {prev:.2f} to {curr:.2f} at turn {i + 1}"
                )

    return failures


def main() -> int:
    print("\nHypothesis Coherence Check — 5-turn session, escalating quality")
    print("=" * 60)
    _, snapshots = asyncio.run(run_session(ANSWERS, model_tier="sonnet"))

    print("\nHypothesis evolution:")
    _print_table(snapshots)

    failures = _check_coherence(snapshots)
    print("CHECKS:")
    if not failures:
        print("  ALL PASS")
    else:
        for f in failures:
            print(f"  FAIL: {f}")

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
