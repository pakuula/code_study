# Adapter: IPC

## Metadata
- feature_label: IPC
- db_path: out/seL4_analysis.db
- run_id: 1
- status: READY
- method_refs:
  - EXPERT_ROLE_PROMPT.md
  - EXPERT_WORKFLOW_ALGORITHM.md
  - FEATURE_EXTRACTION_GUIDE.md
  - EXPERT_ADAPTER_METHOD.md
- run_info:
  - source_root: /home/nikolay/work/cagent/sample/seL4
  - finished_at: 2026-04-25T22:01:56.569899+00:00
  - stages_completed: discover_files, extract_includes, extract_entities, extract_types, extract_comments, extract_preprocessor, extract_usages, reconcile

## Scope
IPC evidence in seL4 index data, centered on endpoint, notification, reply and message-info flows, with send/recv/reply API families and fastpath touchpoints.

## Seeds
- seed_terms:
  - ipc (source: label, confidence: HIGH)
  - endpoint (source: label, confidence: HIGH)
  - notification (source: label, confidence: HIGH)
  - message (source: label, confidence: HIGH)
  - reply (source: label, confidence: HIGH)
  - send (source: guide-query pattern, confidence: HIGH)
  - recv (source: guide-query pattern, confidence: HIGH)
  - receive (source: guide-query pattern, confidence: HIGH)
  - fastpath (source: DB term validation, confidence: HIGH)

## Entities
- primary_entities:
  - seL4_MessageInfo_t (score: 8, confidence: HIGH, evidence: func_param=90, local_var=66, func_return=5, field=1; detector=tree_sitter)
  - notification_t (score: 7, confidence: HIGH, evidence: func_param=27, local_var=8, field=2; detector=tree_sitter)
  - endpoint_t (score: 5, confidence: HIGH, evidence: func_param=20, local_var=6; detector=tree_sitter)
  - reply_t (score: 8, confidence: HIGH, evidence: local_var=12, func_param=9, func_return=1, field=1; detector=tree_sitter)
- supporting_entities:
  - seL4_IPCBuffer (score: 4, confidence: HIGH, evidence: local_var=3, func_param=1, field=1; detector=tree_sitter)
  - MessageID_t (score: 2, confidence: HIGH, evidence: func_param=2; detector=tree_sitter)

## API
- api_prefixes:
  - seL4_ (evidence: IPC-filtered owner prefix token frequency 21)
  - fastpath_ (evidence: IPC-filtered owner prefix token frequency 9)
  - reply_ (evidence: IPC-filtered owner prefix token frequency 9)
  - performInvocation_ (evidence: IPC-filtered owner prefix token frequency 3)
  - arm_sys_ (evidence: IPC-filtered owner prefix token family present)
  - x64_sys_ (evidence: IPC-filtered owner prefix token family present)
  - x86_sys_ (evidence: IPC-filtered owner prefix token family present)
  - riscv_sys_ (evidence: IPC-filtered owner prefix token family present)
- representative_functions:
  - receiveIPC (evidence: v_call_in in src/object/endpoint.c lines 133..269; HIGH+MEDIUM)
  - doIPCTransfer (evidence: v_call_in in src/kernel/thread.c lines 119..126; HIGH+MEDIUM)
  - cancelIPC (evidence: v_call_in in src/object/endpoint.c lines 312..368; HIGH+MEDIUM)
  - performInvocation_Endpoint (evidence: v_call_in in src/object/objecttype.c lines 790,799; HIGH+MEDIUM)
  - performInvocation_Reply (evidence: v_call_in in src/object/objecttype.c lines 815,821; HIGH+MEDIUM)
  - fastpath_call (evidence: DB fast-term call rows; HIGH/MEDIUM index evidence)

## Lifecycle
- state_symbols:
  - endpoint_ptr_get_state (confidence: MEDIUM, evidence: v_call_in from receiveIPC and cancelIPC)
  - endpoint_ptr_set_state (confidence: MEDIUM, evidence: v_call_in from receiveIPC and cancelIPC)
  - notification_ptr_get_state (confidence: MEDIUM, evidence: v_call_in from receiveIPC)
  - thread_state_ptr_get_tsType (confidence: MEDIUM, evidence: v_call_in from cancelIPC)
  - thread_state_ptr_set_tsType (confidence: MEDIUM, evidence: v_call_in from receiveIPC)
- trigger_symbols:
  - doIPCTransfer (confidence: HIGH, evidence: called from receiveIPC)
  - setThreadState (confidence: HIGH, evidence: called from receiveIPC/cancelIPC)
  - doReplyTransfer (confidence: HIGH, evidence: called from performInvocation_Reply)
  - completeSignal (confidence: HIGH, evidence: called from receiveIPC)
  - reply_push (confidence: HIGH, evidence: called from receiveIPC)

## Variants
- mode_markers:
  - CONFIG_KERNEL_MCS (source: IPC-related raw_context matching config marker; confidence: MEDIUM)
  - CONFIG_ARCH_AARCH32 (source: IPC-related raw_context matching config marker; confidence: MEDIUM)
  - __KERNEL_64__ (source: IPC-related raw_context matching config marker; confidence: MEDIUM)
  - fastpath headers under include/arch/*/*/fastpath/fastpath.h (source: v_type_uses fast rows; confidence: HIGH/MEDIUM)
  - architecture families: arm, x64, x86, riscv (source: owner-name cluster in DB; confidence: MEDIUM)

## Exclusions
- exclusion_terms:
  - IPI/TLB local invalidation helpers (invalidateLocal*, switchLocalFpuOwner, ifence_local) when not tied to endpoint/reply/message transfer
  - ACPI and platform initialization strings containing lexical "in fact" (non-IPC)
  - Boot-only shared-frame metadata not proving IPC shared-memory semantics by itself

## Additional Seed Validation
- shared memory:
  - classification: weak_or_ambiguous
  - evidence: term hits = 16 in v_type_uses, mostly from comments/metadata (`sharedFrames`, `shared_types.h`) and not a strong dedicated IPC shared-memory API path
  - action: keep as caveat only; verification TODO required before treating as IPC feature seed
- fact call:
  - classification: absent
  - evidence: `fact_call_term_in_v_call_in = 0`
  - note: `fact_term_in_v_type_uses = 4` are lexical false matches from comments like "in fact" in ACPI headers, not IPC calls
- local call:
  - classification: weak_or_ambiguous
  - evidence: `local_call_term_in_v_call_in = 27`, but sampled rows are dominated by `invalidateLocal*` and `switchLocalFpuOwner` in SMP/vspace code, not IPC call semantics
  - action: do not include as IPC seed term
- fact-vs-fast ambiguity:
  - classification: resolved_to_fast_only_for_IPC
  - evidence: `fast_call_term_in_v_call_in = 19` plus `fast_term_in_v_type_uses = 108`; `fact_call_term_in_v_call_in = 0`
  - rule: treat `fast*` as valid IPC-adjacent variant markers; treat `fact*` as absent/noise in this run

## Confidence Notes
- All primary/supporting entities above are index-derived from v_type_uses with detector `tree_sitter`, confidence `HIGH`.
- Call-flow assertions use v_call_in rows with mixed HIGH and MEDIUM confidence; MEDIUM rows require manual source verification before claiming behavior.
- No IPC-name ambiguity groups were found in `entities` for run_id=1 under filters `%send%|%recv%|%reply%|%endpoint%|%notification%|%fast%|%ipc%`.
- Additional seed checks are lexical and index-derived; treat shared/local seeds as verification-required.

## Ready-to-Use Query Params
- primary_entities: ['seL4_MessageInfo_t', 'notification_t', 'endpoint_t', 'reply_t']
- entity_pool: ['seL4_MessageInfo_t', 'notification_t', 'endpoint_t', 'reply_t', 'seL4_IPCBuffer', 'MessageID_t']
- prefixes: ['seL4_%', 'fastpath_%', 'reply_%', 'performInvocation_%', 'arm_sys_%', 'x64_sys_%', 'x86_sys_%', 'riscv_sys_%']
- representative_functions: ['receiveIPC', 'doIPCTransfer', 'cancelIPC', 'performInvocation_Endpoint', 'performInvocation_Reply', 'fastpath_call']
- mode_markers: ['%CONFIG_KERNEL_MCS%', '%CONFIG_ARCH_AARCH32%', '%__KERNEL_64__%', '%fastpath%']
- seed_terms: ['ipc', 'endpoint', 'notification', 'message', 'reply', 'send', 'recv', 'receive', 'fastpath']
- exclusion_terms: ['%invalidateLocal%', '%switchLocalFpuOwner%', '%ifence_local%', '%in fact%']
