"""System prompt builder for the interviewer node."""

import json
from agent.state import InterviewState

# Competency areas the interviewer should probe
COMPETENCIES = [
    "leadership",
    "technical_depth",
    "agentic_systems",
    "customer_empathy",
    "strategic_thinking",
]

# ---------------------------------------------------------------------------
# Static context — never changes within a session; safe to cache
# ---------------------------------------------------------------------------


def build_static_prompt(cv_text: str, jd_text: str) -> str:
    """Return the static portion of the system prompt (JD + CV + invariant instructions).

    Placed in a cached system block — nothing here changes across turns.
    Includes role/tool instructions so the block reliably exceeds the 2048-token
    minimum required for Sonnet/Haiku cache writes.
    """
    return (
        f"ROLE BEING INTERVIEWED FOR:\n{jd_text}\n\n"
        f"CANDIDATE CV:\n{cv_text}\n\n"
        "---\n"
        "You are a senior technical hiring manager conducting an interview for the role "
        "described above in the job specification.\n\n"
        "COMPETENCY AREAS:\n"
        + "\n".join(f"  - {c}" for c in COMPETENCIES)
        + "\n\n"
        "TOOLS AVAILABLE:\n"
        "  evaluate_answer(question, answer)             — Haiku-powered structured evaluation\n"
        "  update_hypotheses(hypotheses)                 — Store your updated mental model\n"
        "  generate_question(category, depth, rationale) — Sonnet-powered question generation\n"
        "  end_interview(rationale)                      — Use when you have enough signal to assess\n\n"
        "TOOL USAGE RULES:\n"
        "  - Call evaluate_answer BEFORE update_hypotheses (you need the evaluation to update).\n"
        "  - You may call tools in any order the situation demands.\n"
        "  - You may call generate_question without evaluate_answer if you're asking a follow-up.\n"
        "  - Call end_interview instead of generate_question when done — do not do both."
    )


# ---------------------------------------------------------------------------
# Dynamic context — changes every turn; must NOT be cached
# ---------------------------------------------------------------------------


def build_dynamic_prompt(state: InterviewState) -> str:
    """Return the dynamic portion of the system prompt.

    Contains candidate profile, current hypotheses, Q&A history, tool rules,
    and the per-turn instruction. Changes on every interviewer turn.
    """
    candidate = state["candidate"]
    hypotheses = state["hypotheses"]
    answers = state["answers"]
    questions_remaining = state["questions_remaining"]

    # Summarise known hypotheses for the interviewer
    hyp_lines = []
    for comp, h in hypotheses.items():
        hyp_lines.append(
            f"  {comp}: signal={h['signal']}, confidence={h['confidence']:.0%}"
            + (f" — {h['notes']}" if h.get("notes") else "")
        )
    hypotheses_block = "\n".join(hyp_lines)

    # Compact Q&A history
    if answers:
        qa_lines = []
        for i, rec in enumerate(answers, 1):
            eval_summary = rec["evaluation"].get("summary", "")
            score = rec["evaluation"].get("score", "?")
            verdict = rec.get("judge_verdict")
            judge_note = ""
            if verdict:
                if verdict["verdict"] == "flag":
                    adj = verdict.get("adjusted_score")
                    judge_note = f" ⚠ judge flagged (adjusted={adj}): {verdict['critique']}"
                else:
                    judge_note = " ✓ judge accepted"
            qa_lines.append(
                f"  Q{i} [{rec['evaluation'].get('confidence','?')} confidence, score {score}/10]{judge_note}: "
                f"{rec['question'][:80]}...\n"
                f"      → {eval_summary}"
            )
        qa_block = "\n".join(qa_lines)
    else:
        qa_block = "  (none yet — this is the opening of the interview)"

    # Opening instruction differs based on whether this is the first turn
    if not answers:
        turn_instruction = (
            "This is the START of the interview. The candidate has not answered any questions yet.\n"
            "Begin by using generate_question to ask your first question. "
            "Do NOT greet the candidate — go straight to your first question."
        )
    else:
        last = answers[-1]
        turn_instruction = (
            f"The candidate just answered your last question.\n"
            f"Their answer: \"{last['answer']}\"\n\n"
            "THINK (using your extended thinking):\n"
            "1. What signal does this answer give about the candidate?\n"
            "2. Call evaluate_answer to get a structured evaluation.\n"
            "   The tool result contains both 'evaluation' (Haiku's score) and 'judge_verdict'\n"
            "   (Sonnet's adversarial review). If the judge flagged the evaluation, weight\n"
            "   the adjusted_score over the raw score when updating hypotheses.\n"
            "3. Call update_hypotheses with your revised mental model.\n"
            "4. Decide: probe deeper here, switch competency, or end the interview.\n"
            "5. If continuing, call generate_question. If done, call end_interview."
        )

    return f"""CANDIDATE PROFILE:
  Name: {candidate.get('name', 'Candidate')}
  Background: {candidate.get('background', 'Not provided')}
  Current role: {candidate.get('current_role', 'Not provided')}

YOUR GOAL:
Form a complete picture of this candidate's readiness across five competency areas. \
You have {questions_remaining} questions remaining. Be strategic, not formulaic. \
You do not need to use all remaining questions if you have sufficient signal.

YOUR CURRENT HYPOTHESES:
{hypotheses_block}

INTERVIEW HISTORY ({len(answers)} questions asked so far):
{qa_block}

---
{turn_instruction}"""


# ---------------------------------------------------------------------------
# Judge prompt — adversarial critique of the Haiku evaluator's output
# ---------------------------------------------------------------------------


def build_judge_prompt(question: str, answer: str, evaluation: dict) -> str:
    """Return a prompt that asks Sonnet to adversarially validate a Haiku evaluation.

    The judge checks four things:
      1. Are the cited signals actually present in the answer?
      2. Are the gaps fair for the role being interviewed for (not nitpicky)?
      3. Is the score calibrated (7 = strong hire signal for this role)?
      4. Is the stated confidence level justified by the answer's clarity?

    Returns a structured verdict: accept (evaluation is fair) or flag (needs adjustment).
    """
    return (
        "You are a calibration judge reviewing an AI evaluator's assessment of a job interview answer. "
        "Your job is to find flaws — be adversarial, not charitable.\n\n"
        "ROLE: the role described in the job specification above\n\n"
        f"INTERVIEW QUESTION:\n{question}\n\n"
        f"CANDIDATE'S ANSWER:\n{answer}\n\n"
        f"EVALUATOR'S ASSESSMENT:\n{json.dumps(evaluation, indent=2)}\n\n"
        "Critique this assessment on four dimensions:\n"
        "1. SIGNAL ACCURACY — Are the listed signals actually present in the answer, or are they inferred/hallucinated?\n"
        "2. GAP FAIRNESS — Are the gaps valid for this seniority and role, or are they nitpicky or irrelevant?\n"
        "3. SCORE CALIBRATION — Is the score appropriate? 7 = clear hire signal, 5 = borderline, 3 = weak.\n"
        "4. CONFIDENCE VALIDITY — Is the confidence level (low/medium/high) justified by how clearly the answer demonstrated the competency?\n\n"
        "If the evaluation is fair and well-calibrated, return verdict='accept' with a brief confirmation.\n"
        "If there is a meaningful flaw (over-scoring, under-scoring, hallucinated signals, unfair gaps), "
        "return verdict='flag' with a concise critique and an adjusted_score.\n"
        "Only flag if the issue is material — minor wording differences do not warrant a flag."
    )


# ---------------------------------------------------------------------------
# Combined builder — used by mock/ollama adapters that expect a plain string
# ---------------------------------------------------------------------------


def build_system_prompt(state: InterviewState) -> str:
    """Return the full system prompt as a single string.

    Used by mock and ollama adapters. The real Anthropic path uses
    build_static_prompt() + build_dynamic_prompt() as separate cached blocks.
    """
    return build_static_prompt(state["cv_text"], state["jd_text"]) + "\n\n" + build_dynamic_prompt(state)
