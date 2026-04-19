"""
Cache token verification — 10-turn session measuring reads vs writes at scale.

Runs a full 10-turn session with realistic-length CV+JD texts (≥8192 chars
combined so the static block meets _CACHE_MIN_CHARS) and verifies that cache
reads dominate writes after warmup, converting the architectural cost claim
into a measured fact.

Usage:
    uv run python scripts/cache_verification.py
"""
import asyncio
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import agent.models as _models
import agent.nodes as _nodes
from agent.prompts import build_static_prompt
from agent.nodes import _CACHE_MIN_CHARS
from scripts.headless_runner import run_session

_SEP = "=" * 70
_INNER = "-" * 70

# ---------------------------------------------------------------------------
# Long sample texts — each ~4000 chars so build_static_prompt() output >= 8192
# ---------------------------------------------------------------------------

_LONG_CV = """
Brad Bosher — Engineering Leader & Manager of Solutions Architecture

PROFESSIONAL SUMMARY
Senior engineering leader with 15+ years spanning hands-on software development,
distributed systems architecture, and enterprise pre-sales technical leadership.
Known for building high-performing SA teams, driving technical win rates, and
translating deep technical capability into measurable commercial outcomes.
Track record of leading through ambiguity in fast-moving AI/ML product environments.
Trusted advisor to C-level stakeholders at Fortune 500 accounts.

PROFESSIONAL EXPERIENCE

Director of Solutions Architecture | CloudScale Inc | 2021–Present
- Built and scaled a 14-person SA team across EMEA and North America from scratch;
  reduced time-to-first-demo from 3 weeks to 4 days through playbook standardisation
- Drove $42M ARR pipeline in FY2023; achieved 68% technical win rate on competitive deals
- Established quarterly competency assessments and individual development plans for all SAs;
  promoted 4 ICs to senior level within 18 months through structured growth programmes
- Led adoption of Claude API for internal deal-desk automation, cutting proposal cycle by 40%
- Partnered with Product to introduce 6 field-sourced features into the roadmap in 18 months,
  representing $8M in expansion ARR from directly influenced enterprise segments
- Owned hiring: defined hiring bar, conducted loop calibration sessions, reduced mis-hires
  from 30% to 8% by introducing structured technical interview rubrics and debrief frameworks

Senior SA Manager | VectorDB Corp | 2018–2021
- Managed a 9-person team of Solutions Architects focused on financial services vertical
- Designed a voice-of-customer programme feeding weekly field signals to product; directly
  influenced 3 major product pivots away from low-adoption features
- Coached 2 SAs through promotions to staff-level by developing their systems thinking and
  executive communication skills via structured mentoring with measurable milestones
- Drove technical validation frameworks for multi-cloud deployments; reduced POC duration
  by 55% through repeatable evaluation templates and pre-built integration libraries
- Delivered $28M in closed ARR in 2020, 140% of quota, highest-performing SA manager

Principal Solutions Architect | DataStream Systems | 2015–2018
- Individual contributor in enterprise data infrastructure pre-sales; supported $60M+ in deals
- Built reference architectures for real-time streaming pipelines serving healthcare, fintech,
  and logistics; became internal SME for Kafka-based event processing at scale
- Mentored 3 junior SAs on discovery methodology and executive storytelling; all 3 later
  promoted to senior roles
- Designed POC evaluation framework adopted company-wide; became standard for new hires

Senior Engineer | OpenRoute Technologies | 2011–2015
- Led backend engineering for a distributed route-optimisation platform serving 40M daily users
- Migrated monolithic Rails codebase to event-driven microservices on AWS (SQS, ECS, RDS);
  reduced deployment cycle from weekly to continuous with 99.97% uptime maintained throughout
- Built LLM-powered internal support triage tool (GPT-3 era); reduced tier-1 ticket volume 35%

TECHNICAL EXPERTISE
Languages: Python, Go, TypeScript, SQL
Infrastructure: AWS (ECS, Lambda, RDS, SQS), GCP, Terraform, Docker, Kubernetes
AI/ML: Anthropic Claude API, LangGraph, RAG pipelines (hybrid dense/sparse retrieval, BM25),
       LangChain agents, vector databases (Pinecone, Weaviate, pgvector), LLM eval frameworks
Architecture: event-driven microservices, CQRS, distributed caching, multi-tenant SaaS

EDUCATION
M.Sc. Computer Science, University of Edinburgh, 2009
B.Sc. Mathematics and Computer Science, University of Bristol, 2007

CERTIFICATIONS
AWS Solutions Architect — Professional
Google Cloud Professional Data Engineer
Anthropic Certified Partner (2024)
"""

_LONG_JD = """
Manager of Solutions Architects — Anthropic
Location: San Francisco, CA (Hybrid) or Remote (US/UK/EU)
Reporting to: Head of Solutions Engineering

ABOUT ANTHROPIC
Anthropic is an AI safety company working to build reliable, interpretable, and steerable AI
systems. Our Claude models are deployed by some of the world's most sophisticated enterprises
to power mission-critical workflows. We're expanding our Solutions Architecture leadership to
match the scale of enterprise demand.

THE ROLE
We are hiring an experienced Manager of Solutions Architects to lead a growing team of
enterprise-facing SAs who help customers adopt and deploy Claude across agentic, analytical,
and customer-facing applications. This is a player-coach role at a pivotal stage — you will
own the technical win rate for a defined segment, develop a team of highly technical SAs, and
serve as the primary technical voice from the field into our product and go-to-market teams.

You will work directly with VP-level buyers and AI/ML platform engineers at Fortune 500
accounts, translating Anthropic's research capabilities into concrete architectural guidance,
production deployment patterns, and measurable customer outcomes.

WHAT YOU'LL DO

People Leadership
- Hire, onboard, and develop a team of 4–8 Solutions Architects across regions
- Establish a structured coaching programme including individual development plans,
  shadow/co-delivery/solo progression, and quarterly capability reviews
- Set the performance bar: define what great looks like for a senior SA at Anthropic
  and create repeatable frameworks for getting junior SAs there faster
- Build the team's capacity in agentic systems, prompt engineering, and LLM evaluation

Customer and Commercial Impact
- Own the technical win rate and technical health score for your segment
- Lead complex, multi-stakeholder POCs and technical evaluations at strategic accounts
- Be a trusted advisor: understand customer architecture deeply enough to anticipate problems
  before they surface; guide deployment decisions with long-term production thinking
- Travel up to 30% for key accounts, executive briefings, and industry events

Field-to-Product
- Run a structured programme to capture field signal (gaps, objections, use-case patterns)
  and translate it into product input for our Applied and Research teams
- Maintain close relationships with Product, Research, and Engineering to give customers
  accurate long-horizon product guidance and to pull in roadmap items the field is asking for

Technical Leadership
- Stay current on frontier LLM capabilities, agentic system design patterns, and
  emerging deployment architectures (multi-agent, RAG, tool use, computer use)
- Produce internal technical content: reference architectures, POC templates,
  evaluation frameworks, and battle cards used across the SA organisation globally

WHAT WE'RE LOOKING FOR

Required
- 8+ years in technical pre-sales, solutions engineering, or customer-facing architecture roles
- 3+ years managing a team of Solutions Architects or equivalent technical customer-facing team
- Deep experience with LLM-powered products: you have built or deployed agentic systems,
  RAG pipelines, or LLM evaluation frameworks in a customer or internal context
- Demonstrable track record of developing technical talent: specific examples of ICs you
  coached to promotion or next-level performance
- Strong executive communication: comfortable leading briefings with C-suite buyers and
  translating technical nuance into business impact language
- Experience influencing product roadmap from field signal at a product-led growth company

Preferred
- Prior experience with Anthropic Claude API or other frontier model APIs
- Background in multi-agent orchestration frameworks (LangGraph, CrewAI, AutoGen)
- Familiarity with AI safety considerations in enterprise deployment contexts
- Experience scaling an SA team through a hypergrowth phase (0→10 or 5→20)

COMPENSATION
Base salary: $200,000–$260,000 (US); adjusted by region for non-US
Equity: meaningful RSU grant; Anthropic's standard 4-year vest with 1-year cliff
Benefits: top-tier health, generous PTO, $5,000/year learning and development budget,
          remote-work equipment stipend, annual company retreat

WHY THIS ROLE
Anthropic is at an inflection point: enterprise adoption of Claude is accelerating and the
SA team is a critical lever in how we win, retain, and expand strategic accounts.
This manager role carries real influence — over hiring bar, over team culture, over the
technical stories we tell in market, and over what features land on the roadmap.
"""

# ---------------------------------------------------------------------------
# 10 varied answers — spread across all competency areas to avoid early session end
# ---------------------------------------------------------------------------

ANSWERS = [
    # T1 — leadership (weak): forces probe
    "I just figure it out as we go. Leadership is about instinct, not process.",
    # T2 — technical_depth (strong)
    (
        "At Salesforce I redesigned our RAG pipeline — switched from BM25 to hybrid "
        "dense/sparse retrieval, dropping p95 latency from 4s to 800ms. Built a custom "
        "reranker calibration loop triggered on negative-feedback events, with nightly "
        "re-calibration jobs. Deployed via canary strategy: 5% traffic for two weeks, "
        "monitoring precision@5 and user satisfaction scores before full rollout."
    ),
    # T3 — agentic_systems (adequate)
    "I've used LangChain agents for some internal tooling but haven't built one from scratch.",
    # T4 — customer_empathy (strong)
    (
        "A fintech CTO asked us to make the chatbot faster. I dug into their support tickets "
        "and found 60% of escalations were about a 3-step onboarding flow that had nothing to "
        "do with response latency. I mapped the friction points, got buy-in from their product "
        "lead, and we rebuilt the flow instead. Support volume dropped 40% in 6 weeks."
    ),
    # T5 — leadership (strong, to counterbalance T1)
    (
        "I inherited a mid-level SE who struggled with discovery calls. I paired with him "
        "weekly for 3 months using a structured coaching framework — shadowing, co-delivery, "
        "solo with async feedback loops. He passed his AE-to-SE transition assessment 4 months "
        "later and is now the top performer in EMEA. I still use that framework for every new hire."
    ),
    # T6 — strategic_thinking (adequate)
    "I use structured frameworks like DACI to align stakeholders before committing to a direction.",
    # T7 — agentic_systems (strong)
    (
        "I built a lead-qualification agent using LangGraph: it scraped firmographics, called "
        "our internal scoring API, and autonomously routed leads to either a nurture sequence "
        "or an AE assignment. Key challenge was hallucination in the reasoning step — fixed "
        "with structured output schema and two weeks of shadow-mode validation before going live. "
        "Monitored drift weekly via a sample-review pipeline, with human escalation for edge cases."
    ),
    # T8 — strategic_thinking (strong)
    (
        "When I joined CloudScale the SA team had no field-signal loop. I built a weekly digest "
        "process: SAs logged one objection and one feature request per deal in Salesforce, I "
        "aggregated patterns monthly and presented to the CPO. Within 6 months, three field "
        "requests made the roadmap. Win rate on competitive deals went from 42% to 61% in the "
        "quarters following those releases."
    ),
    # T9 — technical_depth (strong, different angle)
    (
        "I designed a multi-tenant RAG architecture on pgvector where each customer's corpus "
        "was isolated via row-level security. Main challenge was keeping embedding freshness "
        "within SLA as customers uploaded thousands of documents daily. Solved it with an "
        "async ingestion queue (SQS + Lambda), a staleness score per document, and a "
        "priority re-embed pipeline that frontloaded high-traffic docs. P99 query freshness "
        "lag stayed under 90 seconds at 100k documents/tenant."
    ),
    # T10 — customer_empathy (strong, to close out session)
    (
        "At my last company an enterprise customer was threatening to churn over 'poor model "
        "accuracy'. I did a structured discovery: mapped their 40 use cases by volume and "
        "business criticality. Found that 85% of their complaints traced to three edge cases "
        "representing only 2% of total queries. We built a custom routing layer that sent those "
        "three case types to a more capable model tier. Customer satisfaction score went from "
        "3.2 to 4.7 in 60 days and they expanded their contract."
    ),
]


def main() -> int:
    # Pre-flight: confirm static prompt meets cache threshold
    static_text = build_static_prompt(_LONG_CV, _LONG_JD)
    static_len = len(static_text)

    print("\nCache Token Verification — 10-turn session")
    print(_SEP)
    print(f"Static block length: {static_len:,} chars (threshold: {_CACHE_MIN_CHARS:,})")

    threshold_ok = static_len >= _CACHE_MIN_CHARS
    if not threshold_ok:
        print(f"  WARNING: static block {static_len} < threshold {_CACHE_MIN_CHARS} — caching will not fire")
    print()

    # Monkey-patch log_api_usage to capture cache metrics
    _calls: list[dict] = []
    _orig = _models.log_api_usage

    def _capturing(
        *,
        node: str,
        model: str,
        usage,
        duration_ms: float,
        session_id=None,
        turn_number=None,
        extra=None,
    ):
        _orig(
            node=node,
            model=model,
            usage=usage,
            duration_ms=duration_ms,
            session_id=session_id,
            turn_number=turn_number,
            extra=extra,
        )
        _calls.append({
            "node": node,
            "turn": turn_number,
            "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "cache_creation": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        })

    _models.log_api_usage = _capturing
    _nodes.log_api_usage = _capturing  # nodes.py uses a local binding from its own import
    try:
        _, snapshots = asyncio.run(
            run_session(ANSWERS, model_tier="sonnet", cv_text=_LONG_CV, jd_text=_LONG_JD, min_turns=8)
        )
    finally:
        _models.log_api_usage = _orig
        _nodes.log_api_usage = _orig

    turns_run = len(snapshots)

    # Filter to interviewer calls (those have turn_number set)
    interviewer_calls = [c for c in _calls if c["node"] == "interviewer" and c["turn"] is not None]

    # Group by turn
    by_turn: dict[int, dict] = {}
    for c in interviewer_calls:
        t = c["turn"]
        if t not in by_turn:
            by_turn[t] = {"cache_read": 0, "cache_creation": 0}
        by_turn[t]["cache_read"] += c["cache_read"]
        by_turn[t]["cache_creation"] += c["cache_creation"]

    print(f"  {'Turn':>4}  {'Cache Read':>12}  {'Cache Write':>12}  {'Hit %':>7}")
    print(f"  {_INNER}")

    for turn in sorted(by_turn.keys()):
        row = by_turn[turn]
        read = row["cache_read"]
        create = row["cache_creation"]
        total = read + create
        hit_pct = f"{100 * read / total:.1f}%" if total else "  n/a"
        print(f"  {turn:>4}  {read:>12,}  {create:>12,}  {hit_pct:>7}")

    total_read = sum(c["cache_read"] for c in interviewer_calls)
    total_create = sum(c["cache_creation"] for c in interviewer_calls)
    ratio = total_read / total_create if total_create else 0.0

    # Warmup sums: turns >= 2 (after first write, reads should dominate)
    warmup_read = sum(v["cache_read"] for t, v in by_turn.items() if t >= 2)
    warmup_create = sum(v["cache_creation"] for t, v in by_turn.items() if t >= 2)

    print()
    print(f"Aggregate (interviewer node, all turns):")
    print(f"  Total cache read    : {total_read:>10,}")
    print(f"  Total cache creation: {total_create:>10,}")
    print(f"  Read / write ratio  : {ratio:.1f}x")
    print()

    # --- Checks ---
    checks: list[tuple[str, bool]] = []

    checks.append((
        f"static block meets cache threshold (len={static_len:,} >= {_CACHE_MIN_CHARS:,})",
        threshold_ok,
    ))
    checks.append((
        f"cache reads observed (total_read={total_read:,})",
        total_read > 0,
    ))
    checks.append((
        f"warmup reads exceed warmup writes (turns>=2: read={warmup_read:,}, write={warmup_create:,})",
        warmup_read > warmup_create,
    ))
    checks.append((
        f"read/write ratio > 5x  [ratio={ratio:.1f}]",
        ratio > 5.0,
    ))
    checks.append((
        f"session ran >= 8 turns  [turns={turns_run}]",
        turns_run >= 8,
    ))

    print("CHECKS:")
    all_passed = True
    for label, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {label}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("RESULT: ALL PASS — reads dominate writes; caching claim is verified")
    else:
        print("RESULT: FAILURES DETECTED — see detail above")
    print()

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
