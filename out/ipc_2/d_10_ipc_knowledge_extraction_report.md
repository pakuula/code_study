# IPC Knowledge Extraction Report (KE, IPC v2)

## 1. Metadata

- feature_label: IPC
- db_path: out/seL4_analysis.db
- run_id: 1
- source_adapter: out/ipc_2/d_07_ipc.adapter.md
- source_instruction: out/ipc_2/d_08_knowledge-extractor-ipc.instructions.md
- ke_boundary_mode: Layer A + Layer B produced; no Layer C substitution
- status: READY_FOR_FULL_REVIEW

| claim | source_view_or_table | detector | confidence | status |
|---|---|---|---|---|
| Extraction bound to d_07 adapter before query execution. | process_contract + d_07 metadata | manual-rule | HIGH | observed |
| All extraction queries were constrained with run_id=1. | query_policy | manual-rule | HIGH | observed |
| Report structure follows 13-section KE contract from d_08. | d_08 instruction contract | manual-rule | HIGH | observed |
| KE output includes Layer A and Layer B only. | KE_SYSTEM_SYNTHESIZER_BOUNDARY | manual-rule | HIGH | observed |

## 2. Scope

| claim | source_view_or_table | detector | confidence | status |
|---|---|---|---|---|
| IPC scope constrained to endpoint, notification, reply, message-info flows and send/recv/reply families with fastpath touchpoints. | d_07 scope contract | manual-rule | HIGH | observed |
| receiveIPC conditional presence is expressed as ifdef CONFIG_KERNEL_MCS. | entity_presence_conditions + conditional_regions (linked to receiveIPC) | ctags/tree_sitter + preprocessor | HIGH | observed |
| shared lexical seed has no evidence in current index (count=0). | reference_candidates | regex/index query | MEDIUM | observed |
| local lexical seed exists but has low domain specificity (count=22 with 12 call + 10 read entries). | reference_candidates | cscope/regex | MEDIUM | observed |

Scope note: MEDIUM seed-level interpretations are index-derived and require source verification for behavioral conclusions.

## 3. Core Entities

| claim | source_view_or_table | detector | confidence | status |
|---|---|---|---|---|
| seL4_MessageInfo_t is a dominant IPC type in current index coverage (func_param=90, local_var=66). | v_type_uses | tree_sitter | HIGH | observed |
| notification_t participates in API and local contexts (func_param=27, local_var=8). | v_type_uses | tree_sitter | HIGH | observed |
| endpoint_t appears in API and local contexts (func_param=20, local_var=6). | v_type_uses | tree_sitter | HIGH | observed |
| reply_t appears in API and local contexts (local_var=12, func_param=9). | v_type_uses | tree_sitter | HIGH | observed |

Evidence snippet (query-backed): counts from v_type_uses grouped by type_name and use_context for run_id=1.

## 4. Supporting Types

| claim | source_view_or_table | detector | confidence | status |
|---|---|---|---|---|
| seL4_IPCBuffer appears in local_var, func_param, and field contexts (3/1/1). | v_type_uses | tree_sitter | HIGH | observed |
| MessageID_t appears in func_param context (count=2). | v_type_uses | tree_sitter | HIGH | observed |
| enum MessageID_Syscall appears as typedef_target (count=1). | v_type_uses | tree_sitter | MEDIUM | observed |

Evidence snippet (query-backed): supporting type distribution from v_type_uses for run_id=1.

## 5. API Surface

| claim | source_view_or_table | detector | confidence | status |
|---|---|---|---|---|
| seL4_ prefix call-surface shows 38 distinct invoked symbols and 129 call-sites. | v_call_in | cscope-backed call index | MEDIUM | observed |
| reply_ prefix call-surface shows 7 distinct invoked symbols and 29 call-sites. | v_call_in | cscope-backed call index | MEDIUM | observed |
| fastpath_ prefix call-surface shows 3 distinct invoked symbols and 6 call-sites. | v_call_in | cscope-backed call index | MEDIUM | observed |
| performInvocation_ as invoked-name prefix returns 0 rows; performInvocation_* appears as caller-side logic instead. | v_call_in | cscope-backed call index | MEDIUM | observed |
| performInvocation_Endpoint invokes sendIPC at src/object/objecttype.c:790 and :799. | v_call_in | tree_sitter | HIGH | observed |
| performInvocation_Reply invokes doReplyTransfer at src/object/objecttype.c:815 and :821. | v_call_in | tree_sitter | HIGH | observed |
| receiveIPC invokes doIPCTransfer at src/object/endpoint.c:227. | v_call_in | tree_sitter | HIGH | observed |
| fastpath_call has call-site evidence (3) but no entity definition row (0), so confidence is capped at MEDIUM for definition-like statements. | v_call_in + entities | tree_sitter + ctags index cross-check | MEDIUM | observed |

Evidence snippet (query-backed):
- receiveIPC -> doIPCTransfer, cancelIPC, reply_push, setThreadState in src/object/endpoint.c.
- doReplyTransfer -> doIPCTransfer, setThreadState in src/kernel/thread.c.
- fastpath_call callers in arch trap handlers (arm/riscv/x86).

## 6. Representative Workflows

Selection basis: local_var core-entity co-usage and high-evidence call traces.

| claim | source_view_or_table | detector | confidence | status |
|---|---|---|---|---|
| Workflow W1 (receiveIPC path): receiveIPC performs cancelIPC (line 143) -> doIPCTransfer (line 227) -> reply_push (line 251) -> setThreadState updates. | v_call_in | tree_sitter | HIGH | observed |
| Workflow W2 (reply transfer path): doReplyTransfer performs doIPCTransfer (line 159) followed by setThreadState transitions (lines 161,165,176,181). | v_call_in | tree_sitter | HIGH | observed |
| Workflow W3 (endpoint invocation path): performInvocation_Endpoint dispatches to sendIPC at lines 790 and 799. | v_call_in | tree_sitter | HIGH | observed |
| Workflow W4 (reply invocation path): performInvocation_Reply dispatches to doReplyTransfer at lines 815 and 821. | v_call_in | tree_sitter | HIGH | observed |
| Workflow W5 (fastpath entry touchpoint): architecture trap handlers call fastpath_call (arm:150, riscv:197, x86:169). | v_call_in | tree_sitter | MEDIUM | observed |

Top representative workflows selected:
1. receiveIPC call sequence in src/object/endpoint.c.
2. doReplyTransfer sequence in src/kernel/thread.c.
3. performInvocation_Endpoint dispatch to sendIPC in src/object/objecttype.c.
4. performInvocation_Reply dispatch to doReplyTransfer in src/object/objecttype.c.
5. fastpath_call trap-entry touchpoints in src/arch/*/c_traps.c.

MEDIUM note: W5 is call-site evidence only and requires source verification for full semantics.

## 7. Variants and Mode Markers

| claim | source_view_or_table | detector | confidence | status |
|---|---|---|---|---|
| receiveIPC has linked conditional marker ifdef CONFIG_KERNEL_MCS. | entity_presence_conditions + conditional_regions | ctags/tree_sitter + preprocessor | HIGH | observed |
| __KERNEL_64__ marker appears in IPC-adjacent raw contexts (count=4). | v_type_uses | tree_sitter | MEDIUM | observed |
| CONFIG_ARCH_AARCH32 marker appears in IPC-adjacent raw contexts (count=7). | v_type_uses | tree_sitter | MEDIUM | observed |
| fastpath variant indicator remains IPC-adjacent (prefix fastpath_% total call-sites=6). | v_call_in | cscope-backed call index | MEDIUM | observed |

## 8. Lifecycle

| claim | source_view_or_table | detector | confidence | status |
|---|---|---|---|---|
| setThreadState is a high-frequency lifecycle transition touchpoint (count=109). | v_call_in | cscope/tree_sitter mixed index | MEDIUM | observed |
| notification_ptr_get_state appears as a notification state read marker (count=8). | v_call_in | cscope/tree_sitter mixed index | MEDIUM | observed |
| thread_state_ptr_get_tsType appears as thread-state inspection marker (count=7). | v_call_in | cscope/tree_sitter mixed index | MEDIUM | observed |
| endpoint_ptr_set_state appears as endpoint state update marker (count=6). | v_call_in | cscope/tree_sitter mixed index | MEDIUM | observed |
| doIPCTransfer appears as transfer lifecycle trigger (count=2 inbound). | v_call_in | cscope/tree_sitter mixed index | MEDIUM | observed |
| doReplyTransfer appears as reply lifecycle trigger (count=2 inbound). | v_call_in | cscope/tree_sitter mixed index | MEDIUM | observed |

Lifecycle note: marker presence is observed; full state-machine semantics are inferred and verification-required.

## 9. Exclusions Applied

| claim | source_view_or_table | detector | confidence | status |
|---|---|---|---|---|
| invalidateLocal* noise filter retained (0 current matches). | reference_candidates | regex/index query | MEDIUM | observed |
| switchLocalFpuOwner appears in index (12) and is excluded as out-of-scope local/FPU noise. | reference_candidates | regex/index query | MEDIUM | observed |
| ifence_local noise filter retained (0 current matches). | reference_candidates | regex/index query | MEDIUM | observed |
| raw_context phrase in fact appears (3) and is excluded as narrative/comment-style noise. | reference_candidates | regex/index query | LOW | observed |

## 10. Subsystem Overview (implementation-semantic)

| claim | source_view_or_table | detector | confidence | status |
|---|---|---|---|---|
| IPC implementation surface in this index is centered on receiveIPC, sendIPC, doIPCTransfer, doReplyTransfer, and performInvocation dispatch points. | v_call_in + v_type_uses + entities | tree_sitter + ctags + cscope | HIGH | observed |
| Endpoint invocation code dispatches into sendIPC, while reply invocation code dispatches into doReplyTransfer. | v_call_in | tree_sitter | HIGH | observed |
| receiveIPC and doReplyTransfer both transition through transfer and thread-state operations, indicating shared transfer/state-update mechanics. | v_call_in | tree_sitter | HIGH | observed |
| Fastpath touchpoints are present at architecture trap-entry call-sites and should be treated as adjacent call-flow evidence, not entity-definition proof. | v_call_in + entities | tree_sitter + ctags cross-check | MEDIUM | observed |
| Build/runtime variant constraints include ifdef CONFIG_KERNEL_MCS (linked) plus architecture markers (__KERNEL_64__, CONFIG_ARCH_AARCH32) in adjacent contexts. | entity_presence_conditions + conditional_regions + v_type_uses | preprocessor + tree_sitter | MEDIUM | observed |

Boundary note: this section is implementation-semantic only; no policy-level intent claims are asserted.

## 11. Client Use Cases (evidence-backed)

| use_case_id | title | caller_evidence | callee_or_api_family | implementation_goal | conditions_or_variants | status | detector | confidence | verification_note |
|---|---|---|---|---|---|---|---|---|---|
| UC-1 | Endpoint Invocation Dispatch to Send Path | performInvocation_Endpoint -> sendIPC at src/object/objecttype.c:790,799 | sendIPC family | Dispatch endpoint invocation into IPC send path | none in row-level call evidence | observed | tree_sitter (v_call_in) | HIGH | none |
| UC-2 | Reply Invocation Dispatch to Reply Transfer | performInvocation_Reply -> doReplyTransfer at src/object/objecttype.c:815,821 | doReplyTransfer / reply path | Route reply invocation into transfer logic | none in row-level call evidence | observed | tree_sitter (v_call_in) | HIGH | none |
| UC-3 | Receive Path with Transfer and State Transition | receiveIPC -> cancelIPC:143, doIPCTransfer:227, reply_push:251, setThreadState:* in src/object/endpoint.c | receiveIPC + transfer/state ops | Receive-side IPC handling with transfer and scheduling-state updates | linked conditional ifdef CONFIG_KERNEL_MCS | observed | tree_sitter + preprocessor linkage | HIGH | behavior intent beyond call order should be source-verified |
| UC-4 | Reply Transfer Path with State Updates | doReplyTransfer -> doIPCTransfer:159 and setThreadState:* in src/kernel/thread.c | doReplyTransfer + doIPCTransfer | Reply-side transfer followed by thread-state updates | none in row-level call evidence | observed | tree_sitter (v_call_in) | HIGH | none |
| UC-5 | Fastpath Trap Entry into IPC-adjacent Call Flow | ALIGN/c_handle_syscall -> fastpath_call at arch trap files (arm:150, riscv:197, x86:169) | fastpath_call / fastpath_% | Architecture-specific fast syscall entry touchpoint | architecture-specific trap handlers | observed | tree_sitter (v_call_in) + entities cross-check | MEDIUM | call-site only; no entities definition row; verify semantics in source |

Use-case extraction method: caller/callee rows from v_call_in, with type-context checks from v_type_uses for representative functions.

## 12. Confidence and Ambiguity Notes

| claim | source_view_or_table | detector | confidence | status |
|---|---|---|---|---|
| cscope-backed call-surface aggregates are capped at MEDIUM confidence by contract. | v_call_in provenance rule | manual-rule + cscope discipline | HIGH | observed |
| tree_sitter/ctags-backed entity-definition and direct call rows may be HIGH when directly observed and not contradicted. | entities + v_call_in + v_type_uses | tree_sitter/ctags | HIGH | observed |
| fastpath_call remains MEDIUM for definition-level language due to entities miss (0) despite call-site hits (3). | v_call_in + entities | tree_sitter + ctags cross-check | MEDIUM | observed |
| Global ambiguity_groups table is non-empty (5852 groups), but IPC-relevant queried entities in this extraction had 0 ambiguity_group_id hits. | ambiguity_groups + entities | sqlite index metadata | MEDIUM | observed |
| Any MEDIUM/LOW behavioral interpretation in this report is index-derived and requires manual source verification. | epistemic policy (AGENTS + KE contract) | manual-rule | HIGH | observed |

Unresolved IPC ambiguities in this extraction scope: none found in queried IPC entity/function set.

## 13. Verification TODOs

| claim | source_view_or_table | detector | confidence | status |
|---|---|---|---|---|
| Verify fastpath_call semantics in source because evidence is call-site only (entities miss). | v_call_in + entities | tree_sitter + ctags cross-check | MEDIUM | inferred |
| Verify architecture marker interpretation (__KERNEL_64__, CONFIG_ARCH_AARCH32) against concrete preprocessor blocks around IPC paths. | v_type_uses + conditional source files | tree_sitter/preprocessor | MEDIUM | inferred |
| Verify lifecycle intent of setThreadState and state accessor markers beyond frequency counts. | v_call_in | cscope/tree_sitter mixed index | MEDIUM | inferred |
| Verify whether performInvocation_% invoked-name absence is an extractor/indexing artifact versus true call-shape property. | v_call_in | cscope-backed call index | MEDIUM | inferred |
| Verify exclusion rationale for switchLocalFpuOwner in any boundary IPC path reviews. | reference_candidates + source review | regex/index query | MEDIUM | inferred |
| Confirm no hidden IPC ambiguity groups by extending name filters if future scope adds aliases. | entities + ambiguity_groups | sqlite index metadata | MEDIUM | inferred |
| Validate behavior-level interpretation of receiveIPC conditional branch handling under CONFIG_KERNEL_MCS from source logic blocks. | entity_presence_conditions + conditional_regions + source | preprocessor + ctags/tree_sitter | MEDIUM | inferred |
| Recheck LOW-confidence narrative/noise filtering around raw_context phrase in fact if comment parsing strategy changes. | reference_candidates.raw_context | regex heuristic | LOW | inferred |
