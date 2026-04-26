# Review Prompt: Synthesis Review For System Synthesizer Output

## Mode
Synthesis Review

## Inputs
- review_target_label: System Synthesizer report
- producer: System Synthesizer (or equivalent synthesis role)
- db_path: out/seL4_analysis.db
- run_id: 1
- artifacts:
  - <path/to/synth_report.md>
  - <path/to/ke_report_used.md>
  - <path/to/adapter_used.md>
  - <path/to/ke_instruction_used.md>

## Contracts To Enforce
- EXPERT_REVIEWER_ROLE_PROMPT.md
- EXPERT_REVIEWER_WORKFLOW.md
- SYSTEM_SYNTHESIZER_ROLE_PROMPT.md
- KE_SYSTEM_SYNTHESIZER_BOUNDARY.md

## Required Synthesis Checks
1. Contract compliance:
   - required synthesis sections exist
   - source KE artifact and run metadata are explicit
2. Traceability:
   - major conclusions map to KE evidence and/or run_id-scoped DB clarification
   - no detached claims without source mapping
3. Confidence preservation:
   - confidence class does not get silently elevated from KE input
   - inferred statements are explicitly labeled
4. Use-case family consistency:
   - synthesized use-case families are consistent with KE use-case evidence
   - no contradiction with core entity/API/workflow facts from KE
5. Ambiguity and uncertainty handling:
   - unresolved alternatives are preserved or explicitly flagged
   - residual risks and TODOs are included when certainty is limited
6. Overclaim guard:
   - no unsupported architecture-intent assertions presented as observed fact

## Output Format
- Mode: Synthesis Review
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
- FAIL if critical traceability/confidence violations exist.
- PASS_WITH_WARNINGS if non-critical synthesis caveats remain.
- PASS only when all mandatory synthesis checks are satisfied.
