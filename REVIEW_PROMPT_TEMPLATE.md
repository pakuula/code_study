# Review Prompt Template

## Purpose
Reusable task prompt for Expert Reviewer. Fill placeholders and run review in one of two modes.

## Mode
Choose one:
- Preflight Review-Lite
- Full Review

## Inputs
- review_target_label: <text>
- producer: <Expert | Knowledge Extractor>
- db_path: <path>
- run_id: <id>
- artifacts:
  - <path/to/file_1>
  - <path/to/file_2>
  - <path/to/file_3>

## Contracts To Enforce
- role_prompt: EXPERT_REVIEWER_ROLE_PROMPT.md
- workflow: EXPERT_REVIEWER_WORKFLOW.md
- producer_contracts:
  - <path/to/producer_contract_1>
  - <path/to/producer_contract_2>

## Acceptance Criteria
- Contract compliance: required files, sections, and fields exist.
- Evidence traceability: key claims map to evidence basis.
- Confidence hygiene: MEDIUM/LOW marked as verification-required.
- Ambiguity handling: alternatives listed, no forced single candidate.
- Scope discipline: no out-of-scope claims.

## Required Checks
1. Artifact inventory and structure check.
2. Mandatory-field validation.
3. Evidence and confidence audit.
4. Ambiguity audit.
5. Scope drift audit.

## Output Format
- Mode: <Preflight Review-Lite | Full Review>
- Status/Verdict: <READY | NEEDS_FIX | PASS | PASS_WITH_WARNINGS | FAIL>
- Findings:
  - Critical
  - High
  - Medium
  - Low
- Required fixes:
- Residual risks:
- Re-review gate criteria:

## Stop Conditions
- Stop with NEEDS_FIX if preflight blockers exist.
- Stop with FAIL if critical contract/evidence violations exist.
- Otherwise emit PASS or PASS_WITH_WARNINGS with exact remediation list.
