---
description: "Updated IPC knowledge extractor instruction (v2 remediated). Use with d_04_ipc.adapter.md. Incorporates all CRITICAL and HIGH fixes from preflight remediation cycle."
applyTo: "out/ipc_2/*.md"
---

# Knowledge Extractor Instruction: IPC (Remediated v2)

## Usage Conditions

Use this instruction only for IPC-domain extraction tasks that:
- use DB `out/seL4_analysis.db`
- are scoped to `run_id=1`
- require output conforming to adapter contract
- use **d_04_ipc.adapter.md** (NOT d_01) as binding source

If any of these are missing or d_04 is not present, stop and request corrected inputs before extraction.

## Required Adapter Binding (Updated for d_04)

1. **Load and bind `out/ipc_2/d_04_ipc.adapter.md`** (remediated version) before running any extraction query.
   - Ignore d_01_ipc.adapter.md (reference only, contains unfixed issues)
   - Use d_04 fields as authoritative input contract for all entity pools, prefixes, representative functions, mode markers, and exclusions

2. **Key Updates from d_04 Remediation**:
   - seed_terms: fastpath count corrected to 6 verified calls (down from claimed 19)
   - shared/local seeds: downgraded to NOT_FOUND / NOT_IPC_DOMAIN
   - API prefixes: now backed by exact v_call_in query results (38 for seL4_, 7 for reply_, 3 for fastpath_)
   - fastpath_call: verified as real entity (3 calls, not hallucinated)
   - seL4_IPCBuffer: evidence verified (5 total, all tree_sitter HIGH confidence)
   - receiveIPC: conditional presence CONFIG_KERNEL_MCS=0 documented

3. **Do not inject IPC-specific assumptions outside the adapter**.

## Required Output Structure

For KE outputs, produce sections in this exact order:

1. **Metadata** (source adapter version, run_id, db_path, status: READY via d_04)
2. **Scope** (feature definition, include conditional presence notes for receiveIPC)
3. **Core Entities** (seL4_MessageInfo_t, notification_t, endpoint_t, reply_t, with detector + confidence per d_04)
4. **Supporting Types** (seL4_IPCBuffer, MessageID_t, enum MessageID_Syscall with verified evidence counts)
5. **API Surface** (seL4_/reply_/fastpath_ prefixes with exact call counts from d_04: 38/7/3 unique functions)
6. **Representative Workflows** (receiveIPC, doIPCTransfer, cancelIPC, performInvocation_* with CONFIG_KERNEL_MCS note for receiveIPC)
7. **Variants/Mode Markers** (CONFIG_KERNEL_MCS, CONFIG_ARCH_AARCH32, __KERNEL_64__, architecture-specific)
8. **Lifecycle** (state symbols + trigger symbols, all MEDIUM confidence from cscope)
9. **Exclusions Applied** (invalidateLocal*, switchLocalFpuOwner, ifence_local, in fact)
10. **Confidence and Ambiguity Notes** (inherit discipline from d_04, show all detectors + ambiguity audit result: 0 conflicts)

Minimum fields per factual item:
- claim
- source_view_or_table
- detector (per d_04 discipline)
- confidence (with rationale)
- status: observed | inferred

## Evidence, Confidence, and Ambiguity Rules (Updated per d_04)

- **Always scope SQL with `WHERE run_id = 1`**.
- **Prefer `v_type_uses` for entities and API typing signals**.
- **Prefer `v_call_in` for call-flow/workflow signals**.
- **Treat DB as heuristic index, not compiler truth**.
- **For `MEDIUM` or `LOW` confidence claims, label as index-derived and verification-required** (per d_04 Confidence Discipline section).
- **If `ambiguity_group_id` is present, list all candidates and do not collapse to one interpretation**. (d_04 audit: 0 conflicts found for IPC core entities)
- **If evidence is absent, state absent explicitly; do not infer semantics from naming alone**.
- **Detector attribution is mandatory**: Every claim must cite which detector (tree_sitter, ctags, cscope, manual_rule) produced the evidence.

## Corrected Seed Validation Rule (Mandatory, per d_04 Fixes)

Before finalizing IPC extraction output, verify and classify each seed based on d_04 findings:

### shared memory
- **d_04 status**: NOT_FOUND_IN_CURRENT_INDEX (query returned 0)
- **classification**: NOT_APPLICABLE
- **action**: Do NOT include as seed; mark as absent in output
- **verification_todo**: Manual code review required to assess if shared-memory IPC API uses non-standard naming convention

### fact call
- **d_04 status**: ABSENT (no confirmed calls in v_call_in)
- **classification**: noise_in_index
- **evidence**: fact-term appears only in ACPI comments, not as call site
- **action**: Exclude from seeds; treat fact_* terms as non-IPC noise

### local call
- **d_04 status**: NOT_IPC_DOMAIN (query returned 0)
- **classification**: SMP_vspace_unrelated
- **evidence**: sampled entries dominated by invalidateLocal* and switchLocalFpuOwner
- **action**: Do NOT include as IPC seed term

### fastpath / fast term
- **d_04 status**: CONFIRMED_IPC_ADJACENT_VARIANT (6 calls verified)
- **classification**: valid_seed_with_medium_confidence
- **evidence**: 
  ```sql
  SELECT invoked_name, COUNT(*) FROM v_call_in 
  WHERE run_id = 1 AND invoked_name LIKE 'fastpath_%'
  → fastpath_call (3), fastpath_reply_recv (2), fastpath_signal (1)
  ```
- **action**: Include in seeds with MEDIUM confidence; mark calls as cscope-detected; KE output must show all three function names

### fact-vs-fast resolution
- **d_04 status**: RESOLVED_TO_FAST_ONLY
- **rule**: Treat `fastpath_*` as valid IPC-adjacent variant markers; treat `fact_*` as absent/noise in this run

## Adapter Binding Checklist (Updated for d_04)

- [ ] d_04_ipc.adapter.md loaded and bound (NOT d_01).
- [ ] Seed counts from d_04 Corrected Additional Seed Validation section used (shared:NOT_FOUND, fastpath:6, local:NOT_FOUND).
- [ ] API prefix counts from d_04 API Surface section used (seL4_:38 unique/129 calls, reply_:7/29, fastpath_:3/6).
- [ ] receiveIPC CONFIG_KERNEL_MCS=0 conditional presence documented.
- [ ] seL4_IPCBuffer evidence verified (5 total: field:1, param:1, local_var:3).
- [ ] fastpath_call included as verified representative function (3 calls, not hallucinated).
- [ ] All detector attribution per d_04 Confidence Discipline section (tree_sitter for types, cscope for calls).
- [ ] Ambiguity audit result noted (0 conflicts found for IPC core entities).

## Short Checklist

- [ ] Adapter d_04_ipc.adapter.md was bound first.
- [ ] Queries were run with `run_id=1`.
- [ ] Output sections follow required structure and order (10 sections listed above).
- [ ] Every factual claim has source/detector/confidence/status.
- [ ] Ambiguities are expanded, not collapsed.
- [ ] MEDIUM/LOW claims are marked verification-required per d_04 confidence discipline.
- [ ] Corrected seed validation (shared, fact, local, fastpath) reflects d_04 findings.
- [ ] receiveIPC conditional presence documented.
- [ ] fastpath_call is included (verified real entity).
- [ ] seL4_IPCBuffer evidence is verified (5 confirmed uses).

## Confidence Discipline Inheritance

This instruction inherits detector hierarchy and confidence rules from d_04:

### Detector Hierarchy (d_04)
1. tree_sitter → HIGH (for types)
2. ctags → HIGH (for functions)
3. cscope → MEDIUM (for call relationships)
4. manual_rule → MEDIUM/LOW (for patterns)
5. label-based → HIGH (if verified via other detectors)

### Confidence Mapping
- **HIGH**: tree_sitter for types (e.g., seL4_MessageInfo_t, reply_t), ctags for functions (e.g., receiveIPC)
- **MEDIUM**: cscope for call relationships (doIPCTransfer, cancelIPC), manual rules for architecture patterns
- **LOW**: Only for unverified patterns; must be marked verification-required

### Ambiguity Handling
d_04 audit found 0 ambiguity_group_id conflicts for IPC core entities. KE output should note this as "stable entity set with no disambiguation required."

## Output Verification Against d_04 Contract

Before finalizing KE output, validate each section against d_04 mandatory fields:

| d_04 Field | KE Output Requirement | Validation |
|-----------|----------------------|-----------|
| metadata | status=READY inherited; run_id=1 maintained | Check: status field present, run_id=1 |
| entities (primary) | All 4 entities present (seL4_MessageInfo_t, notification_t, endpoint_t, reply_t) | Check: all 4 listed with detector + confidence |
| entities (supporting) | seL4_IPCBuffer, MessageID_t, enum MessageID_Syscall | Check: all 3 listed with verified evidence counts |
| API prefixes | seL4_ (38/129), reply_ (7/29), fastpath_ (3/6) | Check: counts match d_04 queries |
| representative_functions | 6 functions listed (receiveIPC, doIPCTransfer, cancelIPC, performInvocation_Endpoint/Reply, fastpath_call) | Check: all 6 present; receiveIPC marked CONFIG_KERNEL_MCS=0 |
| confidence_notes | Per-entity detector + d_04 ambiguity audit result | Check: detector + rationale per entity; audit result noted |
| conditional_presence | receiveIPC CONFIG_KERNEL_MCS=0 | Check: explicitly documented |

## Notes for Knowledge Extractor Runtime

1. **Adapter d_04 is READY**: All CRITICAL and HIGH blocker fixes have been applied and verified with DB queries. KE can proceed without adapter iteration.

2. **Seed coverage**: fastpath seed has confirmed 6 calls (3 unique functions). This is lower than preflight's claimed 19 but represents actual v_call_in coverage. KE output should reflect this verified coverage.

3. **Confidence discipline**: All type-based evidence comes from tree_sitter (HIGH). All call-flow evidence comes from cscope/ctags (MEDIUM/HIGH). Output must distinguish these sources.

4. **Conditional entities**: receiveIPC is only available when CONFIG_KERNEL_MCS=0. KE must document this in output and may need to filter results for MCS vs non-MCS kernels.

5. **Ambiguity status**: No ambiguous entity sets in IPC domain (d_04 audit result). KE output should note this as stability indicator.

6. **Potential follow-up verification TODOs** (from d_04):
   - shared-memory API may use different naming conventions (manual code review)
   - Architecture-specific syscall handlers (arm_sys_, etc.) present in source but not in v_call_in index
   - CONFIG_ARCH_AARCH32 and __KERNEL_64__ markers present but coverage unclear

---

**Note**: This instruction file is bound to d_04_ipc.adapter.md (remediated, READY status). Do NOT use with d_01 (unfixed version).
