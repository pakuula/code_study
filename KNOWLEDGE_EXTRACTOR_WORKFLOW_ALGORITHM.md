# Knowledge Extractor Workflow Algorithm

Purpose: provide a repeatable KE execution workflow that produces evidence-backed technical extraction, including subsystem overview and client use cases, while respecting reviewer and synthesizer boundaries.

## Inputs
- db_path
- run_id
- feature_label
- adapter artifact (domain-specific)
- consumer instruction artifact
- role and boundary contracts:
  - KNOWLEDGE_EXTRACTOR_ROLE_PROMPT.md
  - KE_SYSTEM_SYNTHESIZER_BOUNDARY.md

## Step 1: Contract Bind
- Confirm all required inputs exist.
- Bind adapter and instruction before any extraction query.
- Load role and boundary contracts.
- If any input is missing, stop and request correction.

## Step 2: Scope and Query Policy Lock
- Lock feature scope from adapter.
- Lock SQL policy: every query must be scoped by run_id.
- Lock epistemic policy:
  - source + detector + confidence for factual claims
  - observed vs inferred labeling
  - MEDIUM/LOW as verification-required

## Step 3: Core Entity Extraction
- Extract primary/supporting entity evidence from v_type_uses and related views.
- Record use_context distribution.
- Keep unresolved discrepancies explicit.

## Step 4: API and Call Surface Extraction
- Extract API surface from v_type_uses and v_call_in.
- Build function-level evidence rows with confidence provenance.
- If primary and fallback views diverge, report both and mark discrepancy.

## Step 5: Representative Workflow Selection
- Select representative functions by entity coverage and evidence richness.
- Build line-ordered evidence snippets for each selected function.
- Identify mandatory/optional steps with confidence notes.

## Step 6: Variants and Conditional Analysis
- Extract compile-time/runtime condition signals.
- Tie conditional statements to evidence-bearing tables.
- Preserve ambiguous or competing variant interpretations.

## Step 7: Subsystem Overview (Layer A)
- Produce implementation-semantic overview:
  - what exists
  - how key parts interact
  - where constraints appear
- Do not claim policy-level intent as observed fact.

## Step 8: Client Use-Case Extraction (Layer B)
- Derive client use cases from:
  - call relations (v_call_in)
  - type usage contexts (v_type_uses)
  - representative workflow evidence
- For each use case, provide:
  - scenario title
  - caller/callee evidence anchors
  - implementation-level goal
  - observed or inferred status
  - detector/confidence provenance
- Add TODOs for MEDIUM/LOW scenario semantics.

## Step 9: Confidence and Ambiguity Audit
- Audit confidence consistency across sections.
- Ensure no confidence up-ranking without evidence.
- Expand ambiguity groups where present.
- Confirm language matches confidence class.

## Step 10: Output Materialization
Materialize KE report according to instruction contract.

Minimum sections expected in current pipeline:
1. Metadata
2. Scope
3. Core Entities
4. Supporting Types
5. API Surface
6. Representative Workflows
7. Variants and Mode Markers
8. Lifecycle
9. Exclusions Applied
10. Subsystem Overview
11. Client Use Cases
12. Confidence and Ambiguity Notes
13. Verification TODOs

Minimum claim fields:
- claim
- source_view_or_table
- detector
- confidence
- status (observed or inferred)

## Step 11: Boundary Compliance Check
- Confirm output contains Layer A and Layer B only.
- Confirm no Layer C replacement (System Synthesizer scope).
- If high-level architecture intent is included, mark as inferred and verification-required.

## Step 12: Reviewer Handoff Packaging
Prepare handoff package for Expert Reviewer:
- KE report path
- adapter path
- instruction path
- db_path
- run_id
- confidence and ambiguity section pointers
- unresolved TODO list

## Output Status
- READY_FOR_FULL_REVIEW when all steps above are satisfied.
- NEEDS_FIX when contract or evidence discipline is violated.

## Prohibited During KE Execution
- No adapter/instruction rewriting inside extraction task.
- No mixing run_id across claims.
- No unsupported semantics or hidden ambiguity.
- No substitution of evidence-backed use cases with speculative narrative.
- No synthesis-role takeover.
