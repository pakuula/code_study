---
description: "Remediated IPC adapter (v3) with C2/C3/C1/H3 blockers resolved using DB-backed evidence."
applyTo: "out/ipc_2/*.md"
---

# Adapter: IPC (Remediated v3)

## Metadata
- feature_label: IPC
- db_path: out/seL4_analysis.db
- run_id: 1
- status: READY
- remediation_cycle: 3
- remediation_date: 2026-04-26
- predecessor_artifacts:
  - out/ipc_2/d_04_ipc.adapter.md
  - out/ipc_2/d_05_knowledge-extractor-ipc.instructions.md
  - out/ipc_2/d_06_expert_reviewer_ipc_revalidation_report.md
- method_refs:
  - EXPERT_ROLE_PROMPT.md
  - EXPERT_WORKFLOW_ALGORITHM.md
  - FEATURE_EXTRACTION_GUIDE.md
  - EXPERT_ADAPTER_METHOD.md

## Scope
IPC evidence in seL4 index data, centered on endpoint, notification, reply and message-info flows, including send/recv/reply API families and fastpath call-flow touchpoints.

Conditional presence note:
- receiveIPC conditional is recorded in DB as directive=ifdef, condition=CONFIG_KERNEL_MCS.
- No DB evidence supports condition string CONFIG_KERNEL_MCS=0.

## Seeds

- seed_terms:
  - ipc (source: label, confidence: HIGH, detector: label-based)
  - endpoint (source: label, confidence: HIGH, detector: label-based)
  - notification (source: label, confidence: HIGH, detector: label-based)
  - message (source: label, confidence: HIGH, detector: label-based)
  - reply (source: label, confidence: HIGH, detector: label-based)
  - send (source: guide-query pattern, confidence: HIGH, detector: manual-rule)
  - recv (source: guide-query pattern, confidence: HIGH, detector: manual-rule)
  - receive (source: guide-query pattern, confidence: HIGH, detector: manual-rule)
  - fastpath (source: DB term validation, confidence: MEDIUM, detector: cscope)

### Corrected Additional Seed Validation (C2)

- shared memory:
  - classification: NOT_FOUND_IN_CURRENT_INDEX
  - query:
    sql
    SELECT COUNT(*) AS shared_count
    FROM reference_candidates
    WHERE run_id = 1 AND name LIKE '%shared%';
  - result: 0
  - confidence: NOT_APPLICABLE

- fastpath calls:
  - classification: CONFIRMED_IPC_ADJACENT_VARIANT
  - query:
    sql
    SELECT COUNT(*) AS fastpath_calls
    FROM v_call_in
    WHERE run_id = 1 AND invoked_name LIKE 'fastpath_%';
  - result: 6
  - confidence: MEDIUM (cscope call-site evidence)

- local seed (blocker fix):
  - classification: PRESENT_BUT_LOW_DOMAIN_SPECIFICITY
  - primary query:
    sql
    SELECT COUNT(*) AS local_count
    FROM reference_candidates
    WHERE run_id = 1 AND name LIKE '%local%';
  - result: 22
  - decomposition query:
    sql
    SELECT candidate_type, access_kind, COUNT(*) AS cnt
    FROM reference_candidates
    WHERE run_id = 1 AND name LIKE '%local%'
    GROUP BY candidate_type, access_kind
    ORDER BY candidate_type, access_kind;
  - decomposition result:
    - call_candidate / call: 12
    - read_write_candidate / read: 10
  - confidence: MEDIUM-LOW
  - rationale: local lexical seed exists in DB (22 rows), but IPC relevance is uncertain because 10 of 22 are non-call entries and lexical local is broad.

- fact vs fast ambiguity:
  - rule: treat fastpath_* as IPC-adjacent call-flow markers; do not treat fact lexical matches as function-level IPC evidence.

## Entities

### Primary Entities

- seL4_MessageInfo_t
  - score: 8
  - confidence: HIGH
  - detector: tree_sitter

- notification_t
  - score: 7
  - confidence: HIGH
  - detector: tree_sitter

- endpoint_t
  - score: 5
  - confidence: HIGH
  - detector: tree_sitter

- reply_t
  - score: 8
  - confidence: HIGH
  - detector: tree_sitter

### Supporting Entities

- seL4_IPCBuffer
  - score: 4
  - confidence: HIGH
  - detector: tree_sitter

- MessageID_t
  - score: 2
  - confidence: HIGH
  - detector: tree_sitter

- enum MessageID_Syscall
  - score: 1
  - confidence: MEDIUM
  - detector: tree_sitter

## API Surface

All prefix counts below are from v_call_in and therefore cscope-derived call-site evidence (MEDIUM max):

- seL4_
  - query:
    sql
    SELECT COUNT(DISTINCT invoked_name) AS unique_functions,
           COUNT(*) AS total_calls
    FROM v_call_in
    WHERE run_id = 1 AND invoked_name LIKE 'seL4_%';
  - result: unique_functions=38, total_calls=129
  - confidence: MEDIUM

- reply_
  - query:
    sql
    SELECT COUNT(DISTINCT invoked_name) AS unique_functions,
           COUNT(*) AS total_calls
    FROM v_call_in
    WHERE run_id = 1 AND invoked_name LIKE 'reply_%';
  - result: unique_functions=7, total_calls=29
  - confidence: MEDIUM

- fastpath_
  - query:
    sql
    SELECT COUNT(DISTINCT invoked_name) AS unique_functions,
           COUNT(*) AS total_calls
    FROM v_call_in
    WHERE run_id = 1 AND invoked_name LIKE 'fastpath_%';
  - result: unique_functions=3, total_calls=6
  - confidence: MEDIUM

## Representative Functions (C1 and C3)

- receiveIPC
  - evidence_class: entity_definition + call_sites
  - definition_query:
    sql
    SELECT COUNT(*) AS receiveipc_entities
    FROM entities
    WHERE run_id = 1 AND name = 'receiveIPC';
  - definition_result: 1
  - conditional_query:
    sql
    SELECT cr.directive, cr.condition
    FROM entity_presence_conditions epc
    JOIN entities e ON epc.entity_id = e.entity_id
    JOIN conditional_regions cr ON epc.conditional_region_id = cr.region_id
    WHERE e.run_id = 1 AND e.name = 'receiveIPC';
  - conditional_result: directive=ifdef, condition=CONFIG_KERNEL_MCS
  - conditional_presence: ifdef CONFIG_KERNEL_MCS
  - confidence: HIGH
  - confidence_rationale: entity-definition evidence exists in entities (ctags class), plus supporting call-site evidence.

- doIPCTransfer
  - evidence_class: call_sites
  - query:
    sql
    SELECT COUNT(*) AS inbound_calls
    FROM v_call_in
    WHERE run_id = 1 AND invoked_name = 'doIPCTransfer';
  - confidence: MEDIUM
  - confidence_rationale: cscope call-site evidence only.

- cancelIPC
  - evidence_class: call_sites
  - query:
    sql
    SELECT COUNT(*) AS inbound_calls
    FROM v_call_in
    WHERE run_id = 1 AND invoked_name = 'cancelIPC';
  - confidence: MEDIUM
  - confidence_rationale: cscope call-site evidence only.

- performInvocation_Endpoint
  - evidence_class: call_sites
  - confidence: MEDIUM
  - confidence_rationale: cscope call-site evidence only.

- performInvocation_Reply
  - evidence_class: call_sites
  - confidence: MEDIUM
  - confidence_rationale: cscope call-site evidence only.

- fastpath_call
  - evidence_class: call_sites_only (no entity-definition row)
  - call_site_query:
    sql
    SELECT COUNT(*) AS fastpath_call_in_v_call_in
    FROM v_call_in
    WHERE run_id = 1 AND invoked_name = 'fastpath_call';
  - call_site_result: 3
  - entity_query:
    sql
    SELECT COUNT(*) AS fastpath_call_in_entities
    FROM entities
    WHERE run_id = 1 AND name = 'fastpath_call';
  - entity_result: 0
  - confidence: MEDIUM
  - confidence_rationale: observed in call graph via cscope; not promoted to HIGH because no entity-definition record in entities.

## Lifecycle

- state_symbols:
  - endpoint_ptr_get_state (confidence: MEDIUM, detector: cscope)
  - endpoint_ptr_set_state (confidence: MEDIUM, detector: cscope)
  - notification_ptr_get_state (confidence: MEDIUM, detector: cscope)
  - thread_state_ptr_get_tsType (confidence: MEDIUM, detector: cscope)
  - thread_state_ptr_set_tsType (confidence: MEDIUM, detector: cscope)

- trigger_symbols:
  - doIPCTransfer (confidence: MEDIUM, detector: cscope)
  - setThreadState (confidence: MEDIUM, detector: cscope)
  - doReplyTransfer (confidence: MEDIUM, detector: cscope)
  - completeSignal (confidence: MEDIUM, detector: cscope)
  - reply_push (confidence: MEDIUM, detector: cscope)

## Variants

- mode_markers:
  - CONFIG_KERNEL_MCS (source: conditional_regions and entity_presence_conditions, confidence: HIGH)
  - CONFIG_ARCH_AARCH32 (source: raw_context marker, confidence: MEDIUM)
  - __KERNEL_64__ (source: raw_context marker, confidence: MEDIUM)

## Exclusions

- exclusion_terms:
  - invalidateLocal*
  - switchLocalFpuOwner
  - ifence_local
  - in fact (comment/noise context)

## Confidence Discipline (H3)

### Confidence Provenance Rules

1. cscope-derived call graph evidence (v_call_in, reference_candidates call_candidate) has MEDIUM maximum confidence.
2. ctags/tree_sitter entity-definition evidence from entities/v_type_uses can be HIGH when detector provenance supports it.
3. Call-site evidence and entity-definition evidence must always be labeled separately as evidence_class.
4. If a symbol is present only in v_call_in and absent in entities, confidence cannot exceed MEDIUM.
5. Wording discipline:
   - For call-site only: use observed in call graph.
   - For entity-definition present: use defined entity with supporting call evidence.
6. For MEDIUM or LOW claims, mark as index-derived and requiring source verification when behavior is asserted.

### Application Audit

- API prefixes seL4_, reply_, fastpath_:
  - source: v_call_in
  - applied confidence: MEDIUM
  - rule check: PASS

- receiveIPC:
  - source classes: entity_definition + call_sites
  - applied confidence: HIGH
  - conditional text form: ifdef CONFIG_KERNEL_MCS
  - rule check: PASS

- fastpath_call:
  - source classes: call_sites_only
  - applied confidence: MEDIUM
  - wording: no entity-definition claim
  - rule check: PASS

## Additional Notes

- Third-cycle remediation was required because cycle-2 local seed logic used an over-restrictive filter and presented a categorical zero.
- receiveIPC conditional wording has been corrected to DB-recorded directive + condition form, removing unsupported =0 wording.
- fastpath_call is retained as representative only as call-flow evidence, not as entity-definition evidence.
- Residual risk: conditional_regions contains both ifdef and ifndef variants for CONFIG_KERNEL_MCS across the codebase; per-function interpretation must always use entity-linked conditional query, not global condition-only scans.

## Ready-to-Use Query Params

- primary_entities: ['seL4_MessageInfo_t', 'notification_t', 'endpoint_t', 'reply_t']
- entity_pool: ['seL4_MessageInfo_t', 'notification_t', 'endpoint_t', 'reply_t', 'seL4_IPCBuffer', 'MessageID_t', 'enum MessageID_Syscall']
- prefixes: ['seL4_%', 'fastpath_%', 'reply_%', 'performInvocation_%']
- representative_functions: ['receiveIPC', 'doIPCTransfer', 'cancelIPC', 'performInvocation_Endpoint', 'performInvocation_Reply', 'fastpath_call']
- mode_markers: ['%CONFIG_KERNEL_MCS%', '%CONFIG_ARCH_AARCH32%', '%__KERNEL_64__%', '%fastpath%']
- seed_terms: ['ipc', 'endpoint', 'notification', 'message', 'reply', 'send', 'recv', 'receive', 'fastpath', 'local']
- exclusion_terms: ['%invalidateLocal%', '%switchLocalFpuOwner%', '%ifence_local%', '%in fact%']

## Blocker Resolution Summary

- C2 local-seed over-filtering: FIXED (local count=22 with auditable broad query and decomposition).
- C3 receiveIPC conditional: FIXED (formatted as ifdef CONFIG_KERNEL_MCS with DB query backing).
- C1 fastpath_call wording: FIXED (call-site evidence only, entity-absence explicitly documented).
- H3 confidence discipline: FIXED (explicit rules plus section-level application audit).
