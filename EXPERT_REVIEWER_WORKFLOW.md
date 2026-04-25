# Expert Reviewer Workflow

Purpose: provide a repeatable validation process for artifacts produced by Expert and Knowledge Extractor.

## Inputs
- Review target artifacts.
- Producer type: Expert or Knowledge Extractor.
- Applicable contracts and guides.
- DB path and run_id when evidence validation is required.

## Step 1: Scope Lock
- Identify review mode:
  - Preflight Review-Lite (for Expert output)
  - Full Review (for Knowledge Extractor output)
- List expected artifacts and acceptance criteria.
- List prohibited outputs or assumptions.

## Step 2: Artifact Inventory
- Confirm all required files exist.
- Confirm section headers and mandatory fields are present.
- Record missing items before deep review.

## Step 3: Contract Compliance Check
- Validate artifact structure against expected contract.
- Validate consumer compatibility of handoff artifacts.
- Validate explicit metadata (feature label, run_id, status where required).

## Step 4: Evidence Traceability Audit
- Sample key claims and verify traceability to data source.
- Ensure claims include confidence labeling.
- For DB-derived claims, verify run_id-scoped basis.

## Step 5: Confidence Hygiene Audit
- Ensure MEDIUM and LOW claims include verification-required caveats.
- Ensure tone does not overstate uncertain evidence.
- Flag categorical language unsupported by confidence.

## Step 6: Ambiguity Audit
- Detect ambiguity-bearing claims.
- Ensure alternatives are explicitly listed.
- Ensure no single-candidate collapse without justification.

## Step 7: Scope Drift Audit
- Check for out-of-scope content.
- Check for domain-specific hardcoding in generic files.
- Check that reviewer recommendations do not replace producer work unless requested.

## Step 8: Decision Synthesis
If mode is Preflight Review-Lite:
- emit status READY or NEEDS_FIX
- list blocking fixes required before consumer run

If mode is Full Review:
- emit verdict PASS, PASS_WITH_WARNINGS, or FAIL
- list findings by severity and required corrections

## Step 9: Re-Review Gate
- Define exact acceptance criteria for next iteration.
- Include minimal fix list to reach READY or PASS.
- Keep residual risk list explicit.

## Output Template
- Mode: Preflight Review-Lite | Full Review
- Status/Verdict: READY | NEEDS_FIX | PASS | PASS_WITH_WARNINGS | FAIL
- Findings:
  - Critical
  - High
  - Medium
  - Low
- Required fixes:
- Residual risks:
- Re-review gate criteria:
