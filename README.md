# PersonaGraph

An AI-powered interview system built to explore **enterprise LLM system design** using LangGraph and the native Anthropic SDK.  

Users upload a CV and job description; the system conducts a structured interview, evaluates responses in real time, and produces a detailed debrief. The project is designed to surface **how LLM systems behave under real constraints: cost, control, and safety**.

---

## Design principles

This project is guided by a small set of explicit design choices:

- **Control over abstraction**  
  Avoid wrapper frameworks that hide model behaviour. System decisions (tool use, routing, caching, retrieval) are exposed and inspectable.

- **Constrain the system, not just the prompt**  
  Data access is enforced structurally (scoped retrieval + sensitivity filtering), not left to prompt instructions.

- **Optimise for cost–quality tradeoffs**  
  Different tasks are routed to different models; prompt structure is designed for caching. Cost is treated as a first-class constraint.

- **Make failure modes visible**  
  The system intentionally surfaces where LLMs fail (e.g. adversarial input, evaluation errors, data leakage risks) and demonstrates mitigations.

- **Observability over convenience**  
  Streaming, reasoning traces, retrieval scope, and cache metrics are exposed to make system behaviour transparent.

---

## Why this project exists

Interviewing is a useful proxy for enterprise AI systems: it requires multi-turn reasoning, structured evaluation, tool use, and controlled context.  

This project was built to explore those patterns **without abstraction**, focusing on:
- how models make decisions  
- how context is constructed and constrained  
- how systems fail under adversarial input  
- how cost and quality tradeoffs are managed in practice  

---

## Architecture highlights

### Native Anthropic SDK (no abstraction layer)

All model calls use the Anthropic SDK directly. This preserves access to production-critical primitives:

- **Prompt caching** — applied selectively to static system blocks (`cache_control: ephemeral`)
- **Extended thinking** — streamed reasoning exposed to the UI
- **Native tool_use** — tool calls match Anthropic’s exact schema

This avoids the loss of control and visibility introduced by wrapper frameworks.

---

### LangGraph orchestration

The system is structured as a **decision-making loop**, not a fixed pipeline.