# Expert Reviewer: IPC v2 Final Validation Report (d_09)

**Mode**: Preflight Review-Lite  
**Status**: READY  
**Run Date**: 2026-04-26

## Executive Summary
Second re-validation of d_07 and d_08 against d_06 blockers confirms all four blockers are resolved with DB-backed evidence. Contract-mandatory fields are present in both handoff artifacts. This report opens the KE execution gate only.

Clarification:
- This report is a preflight handoff validation, not a quality verdict for KE output.
- KE output quality must be checked by Full Review after d_10 is produced.
- System-level synthesis conclusions must be checked by Synthesis Review after synthesis output is produced.

## Blocker Fix Verification Summary

### C2: Local-Seed Over-Filtering
- Finding: Verified that local seed is no longer over-filtered and is documented with broad-count plus decomposition.
- Result: ✅
- Evidence:
  - SELECT COUNT(*) AS local_count FROM reference_candidates WHERE run_id=1 AND name LIKE '%local%'; -> 22
  - SELECT candidate_type, access_kind, COUNT(*) AS cnt FROM reference_candidates WHERE run_id=1 AND name LIKE '%local%' GROUP BY candidate_type, access_kind ORDER BY candidate_type, access_kind; -> call_candidate/call=12, read_write_candidate/read=10
- Verdict: Fixed

### C3: receiveIPC Conditional
- Finding: Verified receiveIPC conditional wording in d_07 matches entity-linked DB condition form.
- Result: ✅
- Evidence:
  - SELECT cr.directive, cr.condition FROM entity_presence_conditions epc JOIN entities e ON epc.entity_id=e.entity_id JOIN conditional_regions cr ON epc.conditional_region_id=cr.region_id WHERE e.run_id=1 AND e.name='receiveIPC'; -> directive=ifdef, condition=CONFIG_KERNEL_MCS
  - SELECT condition FROM conditional_regions WHERE condition LIKE '%=0%' LIMIT 5; -> no rows
- Verdict: Corrected to ifdef form

### C1: fastpath_call Wording
- Finding: Verified distinction between call-site evidence and entity-definition evidence is explicit and correctly worded.
- Result: ✅
- Evidence:
  - SELECT COUNT(*) AS fastpath_call_in_v_call_in FROM v_call_in WHERE run_id=1 AND invoked_name='fastpath_call'; -> 3
  - SELECT COUNT(*) AS fastpath_call_in_entities FROM entities WHERE run_id=1 AND name='fastpath_call'; -> 0
  - d_07 labels fastpath_call as call_sites_only, confidence MEDIUM, and explicitly avoids entity-definition claim.
- Verdict: Clear distinction

### H3: Confidence Discipline
- Finding: d_07 includes explicit provenance rules and applies them consistently in sampled entries.
- Result: ✅
- Evidence:
  - Rules present:
    - cscope-derived call graph evidence capped at MEDIUM
    - call-site vs entity-definition must be labeled
    - entities and v_type_uses via ctags/tree_sitter can be HIGH
  - Spot checks:
    - seL4_ prefix: MEDIUM, v_call_in (cscope)
    - reply_ prefix: MEDIUM, v_call_in (cscope)
    - fastpath_ prefix: MEDIUM, v_call_in (cscope)
    - receiveIPC: HIGH only when entity-definition evidence exists
    - fastpath_call: MEDIUM with call-site-only wording
- Verdict: Consistent discipline applied

## Contract Compliance Audit

### d_07 Mandatory Fields
| Field | Status | Notes |
|---|---|---|
| Metadata: status field set | ✅ | Present (status READY). |
| Scope: conditional presence noted | ✅ | Includes receiveIPC conditional form. |
| Seeds: corrected with query evidence | ✅ | Includes local=22 and decomposition. |
| Entities: primary + supporting (7 total) | ✅ | 4 primary plus 3 supporting present. |
| API: prefixes with detector attribution | ✅ | v_call_in/cscope and MEDIUM cap stated. |
| Representative functions: confidence per function | ✅ | Present with evidence class and rationale. |
| Confidence Discipline: rules + ambiguity audit documented | ✅ | Rules plus application audit present. |
| Lifecycle: documented | ✅ | State and trigger symbols present. |

### d_08 Mandatory Fields
| Field | Status | Notes |
|---|---|---|
| YAML frontmatter: description, applyTo | ✅ | Present and valid. |
| Adapter binding points to d_07 | ✅ | Explicitly required. |
| Usage conditions adapted to d_07 specifics | ✅ | Includes DB/run_id and d_07 dependency. |
| Output structure contract present | ✅ | Explicitly enumerated and versioned in instruction artifact. |
| Seed validation rule reflects corrected counts | ✅ | local=22 and decomposition included. |

Result: ✅ All present

## Final Verdict
Status: READY
- All 4 blockers (C2, C3, C1, H3) resolved with DB-backed validation.
- Contract compliance passed for d_07 and d_08.
- KE execution can proceed (d_10 onwards), followed by Full Review gate.

## Residual Risks
- DB remains heuristic index (not compiler-semantic truth); behavior-level claims still require source-level verification where semantics are asserted.
- conditional_regions may contain global variant noise; conditional interpretation should continue to use entity-linked joins.
- Future runs may change counts; seed and confidence checks should be re-run per run_id.

## Next Gates (Process Clarification)
1. KE execution using d_07 + d_08 -> produce d_10.
2. Expert Reviewer Full Review for KE output -> PASS/PASS_WITH_WARNINGS/FAIL.
3. Optional synthesis stage.
4. Expert Reviewer Synthesis Review for synthesis output.

## Artifacts Traceability
- d_01/d_02 (cycle 1, NEEDS_FIX)
- d_03 (cycle 1 preflight, 10 findings)
- d_04/d_05 (cycle 2 remediation, NEEDS_FIX)
- d_06 (cycle 2 re-validation, NEEDS_FIX)
- d_07/d_08 (cycle 3 remediation, subject of this report)
- d_09 (this report, cycle 3 final validation)
