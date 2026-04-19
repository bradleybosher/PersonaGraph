"""
Option 1: Score calibration check — Haiku vs Sonnet on evaluate_answer.

Runs the same answer through evaluate_answer with both models across three quality
levels (weak / adequate / strong). Asserts scores are within ±1 of each other.

Usage:
    cd scripts && uv run python score_calibration.py
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import agent.models as _models
from agent.tools import evaluate_answer

QUESTION = (
    "Tell me about a time you led a team through a difficult technical decision. "
    "What was the situation, and how did you approach it?"
)

ANSWERS = {
    "weak": (
        "I usually just make the call and tell people what to do. I'm pretty decisive."
    ),
    "adequate": (
        "I gathered input from the team, listened to different perspectives, "
        "weighed the tradeoffs, and we reached a consensus together before moving forward."
    ),
    "strong": (
        "At my last company we had a fundamental disagreement on microservices vs monolith "
        "for a new customer-facing platform. I ran a structured RFC process over two weeks: "
        "each tech lead wrote a one-pager, we stress-tested assumptions in a joint design "
        "review with the CTO, and I made the final call with explicit DRIs documented. "
        "We shipped a hybrid approach that cut deployment time by 40% and halved on-call "
        "incidents within three months. The team felt heard even where they disagreed."
    ),
}

_SEP = "-" * 74


def _run_with_model(model_key: str, quality: str) -> dict:
    orig = _models._TASK_MODEL_TIER["evaluation"]
    _models._TASK_MODEL_TIER["evaluation"] = model_key
    try:
        return evaluate_answer(QUESTION, ANSWERS[quality], model_tier="haiku")
    finally:
        _models._TASK_MODEL_TIER["evaluation"] = orig


def main() -> int:
    print("\nScore Calibration: Haiku vs Sonnet on evaluate_answer")
    print(_SEP)
    print(f"{'Quality':<10} {'Model':<8} {'Score':>5}  {'Signals':>7}  {'Gaps':>5}  {'Confidence':<12}  Result")
    print(_SEP)

    all_passed = True
    for quality in ("weak", "adequate", "strong"):
        haiku_result = _run_with_model("haiku", quality)
        sonnet_result = _run_with_model("sonnet", quality)

        delta = abs(haiku_result["score"] - sonnet_result["score"])
        passed = delta <= 1

        for model, result in [("haiku", haiku_result), ("sonnet", sonnet_result)]:
            flag = "PASS" if passed else f"FAIL (delta={delta})"
            suffix = flag if model == "sonnet" else ""
            print(
                f"{quality:<10} {model:<8} {result['score']:>5}  "
                f"{len(result.get('signals', [])):>7}  {len(result.get('gaps', [])):>5}  "
                f"{result.get('confidence', '?'):<12}  {suffix}"
            )

        if not passed:
            all_passed = False
            print(f"  !! haiku signals : {haiku_result.get('signals')}")
            print(f"  !! sonnet signals: {sonnet_result.get('signals')}")
            print(f"  !! haiku gaps    : {haiku_result.get('gaps')}")
            print(f"  !! sonnet gaps   : {sonnet_result.get('gaps')}")

        print()

    print(_SEP)
    if all_passed:
        print("RESULT: ALL PASS — Haiku within ±1 of Sonnet on all three quality levels")
    else:
        print("RESULT: DIVERGENCE DETECTED — see detail above")
    print()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
