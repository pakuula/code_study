# Expert Reviewer: IPC v2 Full Review Report (d_11)

Mode: Full Review  
Review target: IPC Knowledge Extractor final report (d_10)  
Producer: Knowledge Extractor  
DB path: out/seL4_analysis.db  
run_id: 1  
Review date: 2026-04-26

## Verdict
PASS_WITH_WARNINGS

Rationale:
- No critical contract or evidence integrity violations were found.
- Key evidence claims in d_10 were validated against run_id=1 DB queries.
- Non-critical quality gaps remain in strict confidence caveat granularity and use-case grounding trace detail.

## Findings By Severity

### Critical
- None.

### High
- Metadata status value deviates from the d_08 pre-output check language.
  - Evidence:
    - d_08 asks to verify metadata status aligns with d_07 status READY.
    - d_10 Metadata uses status READY_FOR_FULL_REVIEW.
  - Assessment:
    - This is not a data-traceability failure, but it is a contract-interpretation mismatch that should be normalized to avoid gate ambiguity.

### Medium
- Verification-required caveats are not consistently attached at per-claim granularity for MEDIUM rows.
  - Evidence:
    - d_10 includes section-level caveats (for example in Scope, Workflows, Lifecycle), but multiple MEDIUM rows in sections such as Variants/Lifecycle/Subsystem are not individually marked verification-required.
  - Impact:
    - Confidence hygiene is mostly correct, but reviewer auditability is weaker than contract-optimal.

- Use-case grounding quality is good on call evidence but only partially explicit for type/workflow anchors per use case row.
  - Evidence:
    - UC rows provide caller/callee evidence and detector/confidence.
    - Section note states type-context checks were used, but per-row type/workflow anchor is not explicitly shown.
  - Impact:
    - Traceability is acceptable, but not maximal for downstream synthesis/review.

### Low
- Ambiguity coverage could be made more explicit by including the exact IPC ambiguity query scope in a dedicated mini-table.
  - Evidence:
    - d_10 states 0 IPC ambiguity hits for queried entities and records global ambiguity count.
  - Impact:
    - No direct correctness issue; mostly transparency improvement.

## Contract Compliance Check

Result: PASS_WITH_WARNINGS

- Required 13 sections exist in d_10 and are in the required order.
- Required factual claim fields are present across factual sections:
  - claim
  - source_view_or_table
  - detector
  - confidence
  - status
- Required use-case fields are present in section 11.
- run_id-scoped basis is explicit in metadata and query-backed narrative.

Warning retained:
- Metadata status normalization issue (READY vs READY_FOR_FULL_REVIEW wording mismatch to d_08 verification line).

## Evidence Traceability Audit

Result: PASS

DB cross-checks (run_id=1) confirm key d_10 claims:
- API prefix surfaces:
  - seL4_: 38 distinct, 129 total (matches d_10)
  - reply_: 7 distinct, 29 total (matches d_10)
  - fastpath_: 3 distinct, 6 total (matches d_10)
- Key workflow/use-case anchors:
  - performInvocation_Endpoint -> sendIPC: src/object/objecttype.c:790,799
  - performInvocation_Reply -> doReplyTransfer: src/object/objecttype.c:815,821
  - receiveIPC -> cancelIPC/doIPCTransfer/reply_push/setThreadState lines match d_10 ordering
- fastpath_call confidence cap basis:
  - v_call_in count = 3
  - entities count = 0
- Conditional linkage:
  - receiveIPC linked to ifdef CONFIG_KERNEL_MCS
- Seed checks:
  - shared lexical seed count = 0
  - local lexical seed count = 22 (12 call + 10 read)
- Ambiguity checks:
  - global ambiguity groups = 5852
  - IPC key-name ambiguity hits = 0

## Confidence and Ambiguity Hygiene

Result: PASS_WITH_WARNINGS

- Strengths:
  - Call-site vs entity-definition distinction is explicitly preserved (notably for fastpath_call).
  - cscope-backed surfaces are correctly kept at MEDIUM.
  - MEDIUM caveats are present in multiple section notes and in UC-5 verification_note.

- Remaining gap:
  - MEDIUM/LOW caveats should be attached more consistently at row level for strict contract hygiene.

## Use-Case Validation Quality

Result: PASS_WITH_WARNINGS

- Use-case section is present and contract-complete.
- All 5 use cases include explicit status, detector, and confidence.
- Use-case narratives are consistent with core API/workflow evidence and do not contradict d_10 core entity/API sections.
- UC-5 (MEDIUM) correctly carries a verification note.

Warning retained:
- Type/workflow grounding is asserted at section level but could be more explicit per use-case row for stronger traceability.

## Layer Boundary Compliance (Layer A/B vs Layer C)

Result: PASS

- d_10 includes Layer A (facts/workflows/variants/lifecycle/confidence notes) and Layer B (client use cases).
- No Layer C policy-level or architecture-intent synthesis is presented as observed fact.
- Subsystem overview remains implementation-semantic and includes caveats where needed.

## Required Fixes

1. Normalize metadata status wording to remove contract ambiguity:
   - either set d_10 metadata status to READY, or
   - document and ratify READY_FOR_FULL_REVIEW as an accepted Full Review input-state in instruction contract text.
2. Add explicit verification-required markers to each MEDIUM/LOW claim row (not only section-level notes).
3. Add per-use-case trace anchors for at least one supporting type/workflow reference (in addition to call evidence), or explicitly state N/A when not applicable.
4. Add a compact IPC ambiguity-scope evidence table (query scope + count) for audit transparency.

## Residual Risks

- The DB remains a heuristic index; behavior semantics still require source-level verification for MEDIUM/LOW interpretations.
- Architecture-marker interpretations (__KERNEL_64__, CONFIG_ARCH_AARCH32) remain adjacency signals unless tied to entity-linked conditional evidence.
- Future run_id changes can alter counts; this review is valid for run_id=1 only.

## Re-Review Gate Criteria

To upgrade from PASS_WITH_WARNINGS to PASS:
- Metadata status mismatch is normalized and documented.
- MEDIUM/LOW row-level verification-required tagging is complete.
- Use-case rows include explicit type/workflow anchors (or explicit N/A rationale).
- Ambiguity scope table is added and consistent with run_id=1 query results.
