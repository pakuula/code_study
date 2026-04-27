# Prompt for Agent: Knowledge Extractor (IPC v2 — Execution)

Use these baseline files first:
- KNOWLEDGE_EXTRACTOR_ROLE_PROMPT.md
- KNOWLEDGE_EXTRACTOR_WORKFLOW_ALGORITHM.md
- FEATURE_EXTRACTION_GUIDE.md
- out/ipc_2/d_07_ipc.adapter.md
- out/ipc_2/d_08_knowledge-extractor-ipc.instructions.md
- KE_SYSTEM_SYNTHESIZER_BOUNDARY.md
- AGENTS.md

## Objective

Execute IPC feature extraction using the validated cycle-3 artifacts (d_07 + d_08) and produce a structured, evidence-backed KE report.

Include implementation-level subsystem overview and evidence-backed client use cases, aligned with KE role contract.

Do not rebuild adapter/instructions in this task. Use d_07 and d_08 as authoritative inputs.

---

## Inputs

- DB path: out/seL4_analysis.db
- run_id: 1
- Adapter: out/ipc_2/d_07_ipc.adapter.md
- KE instruction: out/ipc_2/d_08_knowledge-extractor-ipc.instructions.md

---

## Required Binding Rules

1. Bind to d_07 before any query execution.
2. Follow output structure and confidence rules from d_08.
3. Apply KE role and workflow discipline from KNOWLEDGE_EXTRACTOR_ROLE_PROMPT.md and KNOWLEDGE_EXTRACTOR_WORKFLOW_ALGORITHM.md.
4. Apply AGENTS.md epistemic discipline:
   - DB is heuristic index, not compiler truth.
   - MEDIUM/LOW claims are index-derived and verification-required.
   - If ambiguity_group_id is present, list all candidates.
5. Respect KE_SYSTEM_SYNTHESIZER_BOUNDARY.md:
  - KE must produce Layer A and Layer B outputs.
  - KE must not produce Layer C high-level policy/intent synthesis.
6. Use run_id=1 in every SQL query.

---

## Mandatory Scope Constraints

- IPC scope only (endpoint, notification, reply, message-info, send/recv/reply families, fastpath touchpoints).
- Keep `receiveIPC` conditional wording aligned with d_07 evidence form (`ifdef CONFIG_KERNEL_MCS`).
- Treat `fastpath_call` as call-site evidence (v_call_in) unless entity-definition evidence is explicitly found.
- Preserve seed interpretation from d_07:
  - shared: not found in current index
  - fastpath: confirmed adjacent variant
  - local: present with low domain specificity

---

## Required Output Artifact

Create:
- out/ipc_2/d_10_ipc_knowledge_extraction_report.md

Use this section order exactly:
1. Metadata
2. Scope
3. Core Entities
4. Supporting Types
5. API Surface
6. Representative Workflows
7. Variants and Mode Markers
8. Lifecycle
9. Exclusions Applied
10. Subsystem Overview (implementation-semantic)
11. Client Use Cases (evidence-backed)
12. Confidence and Ambiguity Notes
13. Verification TODOs

Minimum fields per factual item:
- claim
- source_view_or_table
- detector
- confidence
- status (observed or inferred)

---

## Evidence Requirements

For each major section, include query-backed evidence snippets:

- Core Entities / Supporting Types:
  - use v_type_uses (with use_context split)
- API Surface:
  - use v_call_in and/or v_type_uses with prefix filters
- Representative Workflows:
  - use enclosing_function coverage + line-ordered evidence
- Variants / Mode Markers:
  - use conditional regions and marker matches
- Ambiguity:
  - audit ambiguity_group_id and list candidates if present
- Client Use Cases:
  - use caller/callee evidence (v_call_in) and type usage context (v_type_uses)
  - mark each use case as observed or inferred
  - include detector/confidence provenance for decisive scenario statements

Do not include unqueryable claims.

---

## Quality Gate Before Finalizing d_10

- [ ] Adapter binding explicitly states d_07 as source_adapter.
- [ ] All SQL shown or referenced with run_id=1.
- [ ] Confidence levels consistent with detector provenance (cscope-based claims capped at MEDIUM).
- [ ] `receiveIPC` conditional phrasing matches d_07 evidence style.
- [ ] `fastpath_call` is not overstated as entity definition without entities-table proof.
- [ ] Ambiguity section is explicit: either candidate lists or "none found".
- [ ] Subsystem overview stays implementation-semantic and does not claim policy-level intent as fact.
- [ ] Client use cases are evidence-backed and include observed/inferred status.
- [ ] Verification TODOs include all MEDIUM/LOW behavior-level claims.

---

## Delivery Summary (return in final response)

After creating d_10, return:
1. Path to generated report
2. Number of claims produced by section
3. Top 5 representative workflows selected
4. Client use cases extracted (count + one-line titles)
5. Confidence distribution (HIGH/MEDIUM/LOW counts)
6. Any unresolved ambiguity groups
7. Any scope gaps or missing evidence requiring manual follow-up