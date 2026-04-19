"""
Judge calibration — full evaluate_answer → judge_evaluation pipeline on strong answers.

Verifies the Sonnet judge correctly accepts strong answers and doesn't over-flag.
Mirrors score_calibration.py: no graph, direct tool calls, table output + PASS/FAIL.

Usage:
    uv run python scripts/judge_calibration.py
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# Windows consoles default to cp1252; force UTF-8 output to handle LLM Unicode.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agent.tools import evaluate_answer, judge_evaluation

_SEP = "=" * 70
_INNER = "-" * 70

TEST_CASES = [
    {
        "competency": "leadership",
        "question": "Tell me about a time you developed a team member's technical skills.",
        "answer": (
            "I inherited a mid-level SE who struggled with discovery calls. I paired "
            "with him weekly for 3 months using a structured coaching framework — "
            "shadowing → co-delivery → solo with async feedback loops. He passed his "
            "AE-to-SE transition assessment 4 months later and is now the top performer "
            "in EMEA. I still use that framework for every new hire."
        ),
    },
    {
        "competency": "technical_depth",
        "question": "Describe a technically complex system you've built or deployed.",
        "answer": (
            "At Salesforce I redesigned our RAG pipeline — switched from BM25 to hybrid "
            "dense/sparse retrieval, dropping p95 latency from 4s to 800ms. Built a custom "
            "reranker calibration loop triggered on negative-feedback events, with nightly "
            "re-calibration jobs. Deployed via canary strategy: 5% traffic for two weeks, "
            "monitoring precision@5 and user satisfaction scores before full rollout."
        ),
    },
    {
        "competency": "agentic_systems",
        "question": (
            "Walk me through a time you built or operated an LLM-powered system "
            "that took autonomous actions."
        ),
        "answer": (
            "I built a lead-qualification agent using LangGraph: it scraped firmographics, "
            "called our internal scoring API, and autonomously routed leads to either a "
            "nurture sequence or an AE assignment. Key challenge was hallucination in the "
            "reasoning step — fixed with a structured output schema and two weeks of "
            "shadow-mode validation before going live. Monitored drift weekly via a "
            "sample-review pipeline, with human escalation for edge cases."
        ),
    },
    {
        "competency": "customer_empathy",
        "question": "Tell me about a time you understood a customer's problem better than they did.",
        "answer": (
            "A fintech CTO asked us to 'make the chatbot faster'. I dug into their support "
            "tickets and found 60% of escalations were about a 3-step onboarding flow that "
            "had nothing to do with response latency. I mapped the friction points, got "
            "buy-in from their product lead, and we rebuilt the flow instead. Support volume "
            "dropped 40% in 6 weeks. The latency complaint never came back — it was a "
            "symptom, not the problem."
        ),
    },
]


def _run_pipeline(test: dict) -> dict:
    """Run evaluate_answer (Haiku) then judge_evaluation (Sonnet). Returns combined result."""
    evaluation = evaluate_answer(test["question"], test["answer"], model_tier="haiku")
    verdict = judge_evaluation(test["question"], test["answer"], evaluation, model_tier="haiku")
    return {"evaluation": evaluation, "verdict": verdict}


def main() -> int:
    print("\nJudge Calibration: evaluate_answer (Haiku) -> judge_evaluation (Sonnet)")
    print("Strong answers only — judge should accept all of them.")
    print(_SEP)

    results = []
    for i, test in enumerate(TEST_CASES, start=1):
        print(f"\n=== Test {i}: {test['competency']} ===")
        print(f"QUESTION: {test['question']}")
        print(f"ANSWER:   {test['answer'][:120]}{'...' if len(test['answer']) > 120 else ''}")
        print()

        pipeline = _run_pipeline(test)
        ev = pipeline["evaluation"]
        vd = pipeline["verdict"]

        score = ev.get("score", 0)
        signals = ev.get("signals", [])
        gaps = ev.get("gaps", [])
        confidence = ev.get("confidence", "?")
        verdict_str = vd.get("verdict", "?") if vd else "none"
        critique = vd.get("critique", "") if vd else ""
        adj_score = vd.get("adjusted_score") if vd else None

        print("  Haiku evaluation:")
        print(f"    score      : {score}")
        print(f"    signals    : {signals}")
        print(f"    gaps       : {gaps}")
        print(f"    confidence : {confidence}")
        print()
        print("  Sonnet judge:")
        print(f"    verdict    : {verdict_str}")
        print(f"    critique   : {critique}")
        print(f"    adj. score : {adj_score}")
        print()

        score_pass = score >= 7
        judge_pass = verdict_str == "accept"
        overall = score_pass and judge_pass

        reasons = []
        if not score_pass:
            reasons.append(f"Haiku score {score} < 7")
        if not judge_pass:
            reasons.append(f"judge verdict '{verdict_str}' (expected 'accept')")

        status = "PASS" if overall else f"FAIL ({'; '.join(reasons)})"
        print(f"  {status}")
        print(_INNER)

        results.append({
            "competency": test["competency"],
            "score": score,
            "verdict": verdict_str,
            "score_pass": score_pass,
            "judge_pass": judge_pass,
        })

    print()
    passes = sum(1 for r in results if r["score_pass"] and r["judge_pass"])
    total = len(results)

    print(_SEP)
    print(f"Score checks (Haiku score >= 7): {sum(r['score_pass'] for r in results)}/{total} pass")
    print(f"Judge checks (verdict == accept): {sum(r['judge_pass'] for r in results)}/{total} pass")
    print()

    flagged = [r["competency"] for r in results if not r["judge_pass"]]
    if flagged:
        print(f"  Judge flagged: {flagged}")

    all_passed = passes == total
    if all_passed:
        print("RESULT: ALL PASS — judge accepts all strong answers, Haiku scores >= 7")
    else:
        print("RESULT: FAILURES DETECTED — see detail above")
    print()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
