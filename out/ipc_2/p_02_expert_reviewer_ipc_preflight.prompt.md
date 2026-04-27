# Prompt for Agent: Expert Reviewer (IPC v2 Preflight)

Use these baseline files first:
- EXPERT_REVIEWER_ROLE_PROMPT.md
- EXPERT_REVIEWER_WORKFLOW.md
- REVIEW_PROMPT_PREFLIGHT_EXPERT.md

## Mode
Preflight Review-Lite

## Objective
Validate Expert handoff artifacts for IPC v2 before Knowledge Extractor run.

## Inputs
- DB: out/seL4_analysis.db
- run_id: 1
- Artifacts to review:
  - out/ipc_2/ipc.adapter.md
  - out/ipc_2/knowledge-extractor-ipc.instructions.md
- Optional comparison references:
  - out/ipc_1/ipc.adapter.md
  - out/ipc_1/knowledge-extractor-ipc.instructions.md

## Required Checks
1. Contract compliance:
- both artifacts exist
- mandatory sections and fields present
- instruction format is consumer-compatible

2. Evidence discipline:
- adapter claims are evidence-backed and run_id-scoped
- confidence labels are present and consistent

3. Ambiguity and caveats:
- ambiguous facts are not collapsed to one candidate
- MEDIUM/LOW claims are verification-required

4. Additional seeds audit:
- shared memory
- fact call
- local call
- fact call vs fast call ambiguity handled explicitly

## Output Format
Return:
- Mode: Preflight Review-Lite
- Status: READY | NEEDS_FIX
- Findings by severity:
  - Critical
  - High
  - Medium
  - Low
- Blocking fixes before KE run
- Residual risks
- Re-review gate criteria

## Decision Policy
- READY only if there are no preflight blockers.
- NEEDS_FIX if any blocker exists in contract, evidence, confidence, or ambiguity handling.
