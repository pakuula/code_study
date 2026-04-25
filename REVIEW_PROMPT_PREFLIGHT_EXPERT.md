# Review Prompt: Preflight For Expert Output

## Mode
Preflight Review-Lite

## Inputs
- review_target_label: Expert handoff package
- producer: Expert
- db_path: out/seL4_analysis.db
- run_id: 1
- artifacts:
  - EXPERT_ROLE_PROMPT.md
  - EXPERT_WORKFLOW_ALGORITHM.md
  - EXPERT_ADAPTER_METHOD.md
  - FEATURE_EXTRACTION_GUIDE.md
  - adapters/thread_lifecycle.adapter.md

## Contracts To Enforce
- EXPERT_REVIEWER_ROLE_PROMPT.md
- EXPERT_REVIEWER_WORKFLOW.md

## Required Preflight Gates
1. Handoff readiness:
   - adapter exists and has mandatory sections
   - consumer-facing contract/instruction exists where required
2. Mandatory fields present in adapter:
   - metadata
   - primary_entities and supporting_entities
   - API anchors
   - confidence notes
   - ambiguity notes or explicit no-ambiguity statement
   - ready-to-use query params
3. Discipline checks:
   - no unsupported categorical claims for MEDIUM/LOW
   - no ambiguity collapse
   - run_id-scoped evidence basis documented

## Output Format
- Mode: Preflight Review-Lite
- Status: READY | NEEDS_FIX
- Findings by severity
- Blocking fixes before Knowledge Extractor run
- Residual risks
- Re-review gate criteria

## Stop Conditions
- Emit NEEDS_FIX if any handoff blocker exists.
- Emit READY only if all preflight gates pass.
