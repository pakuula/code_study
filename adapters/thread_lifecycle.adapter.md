# Adapter: Thread Lifecycle

## Metadata
- feature_label: Thread Lifecycle
- source_context: out/THREAD_CREATION_ANALYSIS.md
- status: READY

## Scope
Covers lifecycle-oriented behavior around thread object setup, activation, scheduling interaction, blocking and resume-related transitions, with conditional branches for MCS and non-MCS modes.

## Seeds
- seed_terms:
  - thread (source: label)
  - lifecycle (source: label)
  - tcb (source: report)
  - state (source: report)
  - resume (source: report)
  - suspend (source: report)
  - sched_context (source: report)
  - fault (source: report)

## Entities
- primary_entities:
  - tcb_t (confidence: HIGH)
  - thread_state_t (confidence: HIGH)
- supporting_entities:
  - cap_t (confidence: HIGH)
  - sched_context_t (confidence: MEDIUM)
  - notification_t (confidence: MEDIUM)
  - seL4_Fault_t (confidence: MEDIUM)
  - lookup_fault_t (confidence: MEDIUM)
  - word_t (confidence: HIGH)

## API
- api_prefixes:
  - setThreadState
  - invokeTCB_
  - configure_sched_context
  - Arch_initContext
  - setNextPC
  - setRegister
- representative_functions:
  - create_initial_thread
  - init_sys_state

## Lifecycle
- state_symbols:
  - ThreadState_Running
  - ThreadState_Inactive
  - ThreadState_Blocked_OnReceive
  - ThreadState_BlockedOnReply
- trigger_symbols:
  - setThreadState
  - invokeTCB_Resume
  - invokeTCB_Suspend
  - setThreadStateBlockedOnReply

## Variants
- mode_markers:
  - CONFIG_KERNEL_MCS
  - CONFIG_DEBUG_BUILD
  - SMP

## Exclusions
- exclusion_terms:
  - ipc fastpath-only flows not changing thread state
  - unrelated capability derivation outside thread paths

## Confidence Notes
- This adapter is bootstrapped from index-backed evidence in out/THREAD_CREATION_ANALYSIS.md.
- Items marked MEDIUM should be verified against raw_context snippets and call paths.
- Lifecycle states beyond creation and activation may be incomplete if no direct state setter evidence is present in selected functions.

## Ready-to-Use Query Params
- primary_entities: ['tcb_t', 'thread_state_t']
- entity_pool: ['tcb_t', 'thread_state_t', 'cap_t', 'sched_context_t', 'notification_t', 'seL4_Fault_t', 'lookup_fault_t', 'word_t']
- prefixes: ['setThreadState%', 'invokeTCB_%', 'configure_sched_context%', 'Arch_initContext%', 'setNextPC%', 'setRegister%']
- mode_markers: ['%CONFIG_KERNEL_MCS%', '%CONFIG_DEBUG_BUILD%', '%SMP%']
