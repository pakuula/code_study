# Expert Reviewer: IPC v2 Re-validation Report (d_06)

**Mode**: Preflight Review-Lite
**Status**: NEEDS_FIX
**Run Date**: 2026-04-26

## Executive Summary
Re-validation of remediated artifacts `d_04_ipc.adapter.md` and `d_05_knowledge-extractor-ipc.instructions.md` shows meaningful progress: C4 and H2 are resolved with reproducible DB-backed evidence, and most contract sections are present.

However, readiness gate is still blocked by unresolved critical accuracy issues in C2 (local-seed correction remains over-filtered/misleading) and C3 (conditional claim for `receiveIPC` is directionally inconsistent with DB condition representation). Confidence discipline also remains partially inconsistent where cscope-derived claims are elevated or presented as stronger than detector limits allow. Verdict is **NEEDS_FIX**.

## Blocker Fix Verification (C1-C4, H2, H3)

### C1: `fastpath_call` Replacement / Verification
- Location: `d_04`, Representative Functions and summary fix sections.
- Check: Validate whether `fastpath_call` has DB-backed evidence.
- Result: ⚠️ Partially addressed.
- Evidence:
  - `SELECT invoked_name, COUNT(*) FROM v_call_in WHERE run_id=1 AND invoked_name LIKE 'fastpath%' GROUP BY invoked_name;`
    - `fastpath_call=3`, `fastpath_reply_recv=2`, `fastpath_signal=1`
  - `SELECT e.name FROM entities e WHERE e.run_id=1 AND e.name='fastpath_call';`
    - No entity row found.
- Rationale:
  - The original blocker asked for real verification. `fastpath_call` is now DB-backed in `v_call_in`, which is an improvement and satisfies call-graph evidence.
  - But `d_04` labels it as a fully verified entity/function while it is not present in `entities` for `run_id=1`; this should be phrased as call-site evidence only.

### C2: Seed Evidence Count Corrections (`shared`, `fastpath`, `local`)
- Location: `d_04` Corrected Additional Seed Validation section.
- Check: Validate corrected counts and confidence discipline per seed.
- Result: ❌ Not fully corrected (blocking).
- Evidence:
  - Shared:
    - `SELECT COUNT(*) FROM reference_candidates WHERE run_id=1 AND name LIKE '%shared%';` -> `0`
    - `d_04` now reports absence; this part is corrected.
  - Fastpath:
    - `SELECT COUNT(*) FROM v_call_in WHERE run_id=1 AND invoked_name LIKE 'fastpath_%';` -> `6`
    - `d_04` reports `6`; this part is corrected.
  - Local:
    - `d_04` uses narrow filter (`candidate_type='read_write_candidate' AND access_kind='read_write'`) and reports `0`.
    - Broader seed reality check:
      - `SELECT COUNT(*) FROM reference_candidates WHERE run_id=1 AND name LIKE '%local%';` -> `22`
      - `SELECT candidate_type, access_kind, COUNT(*) FROM reference_candidates WHERE run_id=1 AND name LIKE '%local%' GROUP BY candidate_type, access_kind;` -> `call_candidate/call=12`, `read_write_candidate/read=10`
- Rationale:
  - The local-seed correction in `d_04` is over-filtered and presented as categorical absence.
  - This does not satisfy the intent of correcting an inflated count to a truthful, auditable count with transparent query semantics.

### C3: `receiveIPC` CONFIG conditional presence
- Location: `d_04` Scope note and Representative Functions; mirrored in `d_05` usage and checklist sections.
- Check: Validate conditional presence claim and backing query.
- Result: ❌ Not correctly documented (blocking).
- Evidence:
  - DB condition:
    - `SELECT cr.directive, cr.condition FROM entity_presence_conditions epc JOIN entities e ON epc.entity_id=e.entity_id JOIN conditional_regions cr ON epc.conditional_region_id=cr.region_id WHERE e.run_id=1 AND e.name='receiveIPC';`
    - Result: `directive=ifdef`, `condition=CONFIG_KERNEL_MCS`
  - `d_04`/`d_05` repeatedly claim `CONFIG_KERNEL_MCS=0`.
  - `SELECT condition FROM conditional_regions WHERE condition LIKE '%=0%';` -> no rows.
- Rationale:
  - Required conditional note exists, but the specific expression shown in artifacts is not DB-supported and may invert/overstate semantics.

### C4: `seL4_IPCBuffer` Evidence Verification
- Location: `d_04` Supporting Entities.
- Check: Validate counts and methodology.
- Result: ✅ Corrected.
- Evidence:
  - `SELECT use_context, COUNT(*) FROM v_type_uses WHERE run_id=1 AND type_name='seL4_IPCBuffer' GROUP BY use_context;`
    - `field=1`, `func_param=1`, `local_var=3`
  - `SELECT COUNT(*) FROM v_type_uses WHERE run_id=1 AND type_name='seL4_IPCBuffer';` -> `5`
- Rationale:
  - Count and decomposition are now internally consistent and query-backed.

### H2: API Prefix Filtering Methodology
- Location: `d_04` API Surface.
- Check: Verify exact query methodology plus detector/count transparency.
- Result: ✅ Fixed.
- Evidence:
  - `seL4_`: `SELECT COUNT(DISTINCT invoked_name), COUNT(*) ... LIKE 'seL4_%';` -> `38`, `129`
  - `reply_`: `... LIKE 'reply_%';` -> `7`, `29`
  - `fastpath_`: `... LIKE 'fastpath_%';` -> `3`, `6`
- Rationale:
  - Vague "IPC-filtered token frequency" language has been replaced with reproducible SQL and detector labeling.

### H3: Confidence Notes Discipline
- Location: `d_04` Confidence Discipline section; propagated in `d_05`.
- Check: Per-entity detector attribution, rationale, ambiguity audit, and detector-consistent confidence levels.
- Result: ⚠️ Mostly disciplined, with material gaps.
- Evidence:
  - Positives:
    - Detector hierarchy and entity-level rationale provided.
    - API prefix confidence generally constrained to MEDIUM for cscope.
    - Ambiguity audit for IPC-core names documented.
  - Gaps:
    - cscope-derived claims are sometimes presented with stronger language than detector rules justify.
    - Representative function confidence in `d_04` lists several functions as cscope MEDIUM despite ctags HIGH entity evidence existing; confidence provenance is mixed/inconsistent.
    - `fastpath_call` framing as fully verified function entity is stronger than evidence basis (call-site only).
- Rationale:
  - Discipline improved substantially but not yet consistently precise.

## Contract Compliance Audit

### d_04 Mandatory Fields
| Field | Status | Notes |
|---|---|---|
| Metadata: `feature_label`, `db_path`, `run_id`, `status` | ✅ | Present and non-empty. |
| Entities primary/supporting with detector + confidence | ✅ | Present for listed entities. |
| API section with methodology + detector per prefix | ✅ | Query method and detector shown. |
| Representative functions with `file:line` + detector + confidence | ⚠️ | Present, but provenance consistency issues (`fastpath_call` not in `entities`; some line/confidence framing needs tightening). |
| Confidence notes with rationale | ⚠️ | Section exists; some claims overstate evidence precision. |
| Ambiguity notes/audit | ✅ | Explicit audit section included for IPC-core set. |
| Conditional presence for affected entities | ⚠️ | Present, but `CONFIG_KERNEL_MCS=0` wording not DB-supported as written. |

### d_05 Mandatory Fields
| Field | Status | Notes |
|---|---|---|
| YAML frontmatter (`description`, `applyTo`) | ✅ | Present. |
| Adapter binding points to `d_04` (not `d_01`) | ✅ | Explicitly enforced. |
| Usage conditions adapted to `d_04` specifics | ✅ | Present and aligned. |
| Output structure: 10 sections + min fields (`claim`, `source_view_or_table`, `detector`, `confidence`, `status`) | ✅ | Explicitly defined. |
| Seed validation rule reflects corrected seeds | ⚠️ | Reflects d_04 narrative, but inherits unresolved local-seed and conditional-claim issues. |

**Contract Verdict**: **FAIL (gating)** due to unresolved critical correctness issues (C2, C3) despite structural completeness.

## Confidence Discipline Assessment
- Overall: improved vs d_03 baseline, but not yet fully compliant.
- Confirmed strengths:
  - Detector hierarchy is explicit.
  - Most cscope-based API prefix claims are correctly MEDIUM.
- Remaining discipline issues:
  - Evidence category mixing (entity-definition vs call-site evidence) is not always explicit.
  - Some wording implies stronger certainty than detector/source supports.
  - Conditional claim precision (`=0`) is not grounded in recorded condition string.

## Scope Drift Audit
- Status: ✅ No significant scope drift.
- Findings:
  - Domain remains IPC-focused.
  - No major unrelated new seed families introduced.
  - `d_05` structure remains aligned with `d_04` artifacts.

## Ambiguity Audit
- Status: ✅ Documented for IPC-core entities.
- Evidence:
  - Query for IPC-core names in ambiguity groups returned no rows.
  - Note: global ambiguity groups do exist in run (`8` rows total), but not for the audited IPC-core set.

## Re-validation Verdict
- **Status**: NEEDS_FIX
- **Blocking issues**:
  1. C2 local-seed correction must be reworked with non-overfiltered, auditable query semantics and accurate count interpretation.
  2. C3 conditional-presence claim must be corrected to match DB-recorded condition representation (remove unsupported `=0` assertion unless separately proven).
- **Residual risks**:
  - C1 remains partially fragile because `fastpath_call` is verified via call graph but not in `entities`; phrasing should avoid overclaiming entity-level verification.
  - Confidence provenance for representative functions should clearly separate definition evidence (ctags) from call-flow evidence (cscope).
- **Next gate**: Re-run p_03 remediation cycle after above fixes; KE execution should remain blocked until resolved.

## Artifacts Traceability
- `d_03_expert_reviewer_ipc_preflight_report.md`: baseline checklist source
- `d_04_ipc.adapter.md`: remediated adapter under review
- `d_05_knowledge-extractor-ipc.instructions.md`: remediated instruction under review
- `d_06_expert_reviewer_ipc_revalidation_report.md`: this report
