# Review Prompt: Full Review For Knowledge Extractor Output

## Mode
Full Review

## Inputs
- review_target_label: Knowledge Extractor final report
- producer: Knowledge Extractor
- db_path: out/seL4_analysis.db
- run_id: 1
- artifacts:
  - <path/to/final_report.md>
  - <path/to/adapter_used.md>
  - <path/to/consumer_instruction.md>

## Contracts To Enforce
- EXPERT_REVIEWER_ROLE_PROMPT.md
- EXPERT_REVIEWER_WORKFLOW.md
- FEATURE_EXTRACTION_GUIDE.md
- <domain adapter contract>

## Required Full Checks
1. Contract compliance:
   - required sections exist in final report
   - output format matches consumer contract
2. Evidence traceability:
   - key claims mapped to DB-backed evidence
   - run_id-scoped basis is explicit
3. Confidence hygiene:
   - MEDIUM/LOW claims marked verification-required
   - no overconfident wording for weak evidence
4. Ambiguity handling:
   - ambiguity groups expanded where relevant
   - no single-candidate forcing without caveat
5. Scope drift:
   - report stays within requested feature scope
   - no unsupported semantic extrapolation

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
