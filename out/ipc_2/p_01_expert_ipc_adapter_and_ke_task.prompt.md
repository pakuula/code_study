# Prompt for Agent: Expert (IPC v2)

Use these baseline files first:
- EXPERT_ROLE_PROMPT.md
- EXPERT_WORKFLOW_ALGORITHM.md
- FEATURE_EXTRACTION_GUIDE.md
- EXPERT_ADAPTER_METHOD.md

## Objective
From scratch, prepare IPC domain handoff artifacts for Knowledge Extractor.

Do not generate an IPC feature report in this task.

## Inputs
- DB: out/seL4_analysis.db
- run_id: 1
- Optional context hints:
  - out/thread_1/THREAD_CREATION_ANALYSIS.md
  - out/ipc_1/ipc.adapter.md (for comparison only, re-validate everything against DB)

## Required Outputs
Create these files under out/ipc_2:
1. out/ipc_2/ipc.adapter.md
2. out/ipc_2/knowledge-extractor-ipc.instructions.md

## Scope Rules
- Keep FEATURE_EXTRACTION_GUIDE.md domain-neutral.
- Put IPC-specific assumptions only in out/ipc_2/ipc.adapter.md.
- Treat Knowledge Extractor as a consumer contract target, not as a full prompt to recreate.

## Mandatory Adapter Requirements
Adapter must include:
- Metadata
- Scope
- Seeds (with source/provenance)
- Entities
  - primary_entities
  - supporting_entities
- API
  - api_prefixes
  - representative_functions
- Lifecycle (only if evidence supports)
  - state_symbols
  - trigger_symbols
- Variants
  - mode_markers
- Exclusions
- Confidence Notes
- Ready-to-Use Query Params

## Additional Seed Validation
Before finalizing seeds, explicitly check and classify:
- shared memory
- fact call
- local call

For each concept:
- confirmed: add to seed_terms with source and confidence
- weak/ambiguous: add to Confidence Notes with verification TODO
- absent: mark as absent in current index

Also test spelling ambiguity between fact call and fast call.

## IPC Evidence Discovery Hints
Use v_type_uses and v_call_in with run_id=1:
- types: %ipc%, %endpoint%, %notification%, %message%, %reply%, %shared%
- APIs: %send%, %recv%, %receive%, %reply%, %notification%, %endpoint%, %fast%
- transitions: blocking/wakeup/reply/state setter patterns
- variants: CONFIG_* and architecture markers from raw_context

## Specialized Instruction Requirements
File: out/ipc_2/knowledge-extractor-ipc.instructions.md

Must contain:
- clear usage conditions for IPC extraction
- required adapter binding step
- required output structure for KE outputs
- evidence/confidence/ambiguity rules
- short checklist

Use valid YAML frontmatter with:
- description (trigger phrases: IPC, knowledge extractor, adapter, feature extraction)
- applyTo scoped to relevant markdown docs only (no global **)

## Final Response Format
Return:
1. files created/updated
2. rationale for selected entities and prefixes
3. unresolved ambiguities and confidence caveats
4. status of additional seed validation (shared memory, fact/fast call, local call)
