# Prompt for Agent: Expert Reviewer (IPC v2 — Full Review of KE Output)

Use these baseline files:
- EXPERT_REVIEWER_ROLE_PROMPT.md
- EXPERT_REVIEWER_WORKFLOW.md
- REVIEW_PROMPT_FULL_KE.md
- KE_SYSTEM_SYNTHESIZER_BOUNDARY.md

## Objective

Validate KE extraction output quality after execution gate, with explicit checks for:
- evidence traceability
- confidence and ambiguity discipline
- client use-case grounding
- boundary compliance (Layer A + Layer B, no Layer C substitution)

## Mode
Full Review

## Inputs

- review_target_label: IPC Knowledge Extractor final report
- producer: Knowledge Extractor
- db_path: out/seL4_analysis.db
- run_id: 1
- artifacts:
  - out/ipc_2/d_10_ipc_knowledge_extraction_report.md
  - out/ipc_2/d_07_ipc.adapter.md
  - out/ipc_2/d_08_knowledge-extractor-ipc.instructions.md
  - out/ipc_2/d_09_expert_reviewer_ipc_final_validation_report.md

## Contracts To Enforce

- EXPERT_REVIEWER_ROLE_PROMPT.md
- EXPERT_REVIEWER_WORKFLOW.md
- REVIEW_PROMPT_FULL_KE.md
- KNOWLEDGE_EXTRACTOR_ROLE_PROMPT.md
- KNOWLEDGE_EXTRACTOR_WORKFLOW_ALGORITHM.md
- KE_SYSTEM_SYNTHESIZER_BOUNDARY.md

## Required Full Checks

1. Contract compliance:
   - required sections exist in d_10
   - section order matches d_08 contract
   - required claim fields are present

2. Evidence traceability:
   - key claims map to DB-backed evidence
   - run_id-scoped basis is explicit
   - decisive statements reference source_view_or_table

3. Confidence hygiene:
   - MEDIUM/LOW claims marked verification-required
   - no overconfident wording for weak evidence
   - call-site vs entity-definition distinction is preserved

4. Ambiguity handling:
   - ambiguity groups expanded where relevant
   - no single-candidate forcing without caveat

5. Scope drift:
   - report stays within IPC scope and adapter boundaries
   - no unsupported semantic extrapolation

6. Use-case validation:
   - client use cases are present
   - each use case is grounded in call/type/workflow evidence
   - observed vs inferred status is explicit per use case
   - MEDIUM/LOW use-case semantics marked verification-required
   - use-case narrative does not contradict core entity/API evidence

7. Boundary compliance:
   - d_10 includes Layer A + Layer B outputs
   - no Layer C high-level policy/intent synthesis is presented as fact

## Output Artifact

Create:
- out/ipc_2/d_11_expert_reviewer_ke_full_review_report.md

## Output Format

- Mode: Full Review
- Verdict: PASS | PASS_WITH_WARNINGS | FAIL
- Findings by severity:
  - Critical
  - High
  - Medium
  - Low
- Required fixes
- Residual risks
- Re-review gate criteria

## Stop Conditions

- FAIL if critical evidence/contract violations exist.
- PASS_WITH_WARNINGS if non-critical issues remain.
- PASS only when all mandatory checks are satisfied.

## Delivery Summary (return in final response)

After creating d_11, return:
1. Final verdict (PASS | PASS_WITH_WARNINGS | FAIL)
2. Highest-severity findings summary
3. Use-case validation outcome
4. Boundary compliance outcome (Layer A/B vs Layer C)
5. Required fixes (if any)
6. Residual risks and next gate recommendation
