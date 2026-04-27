---
description: "Use for IPC knowledge extractor runs that require adapter-bound feature extraction with confidence and ambiguity discipline. Triggers: IPC, knowledge extractor, adapter, feature extraction."
applyTo: "out/ipc_2/*.md"
---

# Knowledge Extractor Instruction: IPC

## Usage Conditions
Use this instruction only for IPC-domain extraction tasks that:
- use DB `out/seL4_analysis.db`
- are scoped to `run_id=1`
- require output conforming to an adapter contract

If any of these are missing, stop and request corrected inputs before extraction.

## Required Adapter Binding
1. Load and bind `out/ipc_2/ipc.adapter.md` before running any extraction query.
2. Use adapter fields as authoritative input contract for entity pools, prefixes, representative functions, mode markers, and exclusions.
3. Do not inject IPC-specific assumptions outside the adapter.

## Required Output Structure
For KE outputs, produce sections in this exact order:
1. Metadata
2. Scope
3. Core Entities
4. API Surface
5. Representative Workflows
6. Variants/Mode Markers
7. Lifecycle (only when evidence supports)
8. Exclusions Applied
9. Confidence and Ambiguity Notes
10. Verification TODOs

Minimum fields per factual item:
- claim
- source_view_or_table
- detector
- confidence
- status: observed | inferred

## Evidence, Confidence, And Ambiguity Rules
- Always scope SQL with `WHERE run_id = 1`.
- Prefer `v_type_uses` for entities and API typing signals.
- Prefer `v_call_in` for call-flow/workflow signals.
- Treat DB as heuristic index, not compiler truth.
- For `MEDIUM` or `LOW` confidence claims, label as index-derived and verification-required.
- If `ambiguity_group_id` is present, list all candidates and do not collapse to one interpretation.
- If evidence is absent, state absent explicitly; do not infer semantics from naming alone.

## Additional Seed Validation Rule (Mandatory)
Before finalizing IPC extraction output, verify and classify:
- shared memory
- fact call
- local call
- fact-vs-fast ambiguity

Classification policy:
- confirmed: include in seeds/entities with source and confidence
- weak_or_ambiguous: move to caveats with explicit verification TODO
- absent: mark absent_in_current_index

## Short Checklist
- [ ] Adapter `out/ipc_2/ipc.adapter.md` was bound first.
- [ ] Queries were run with `run_id=1`.
- [ ] Output sections follow required structure and order.
- [ ] Every factual claim has source/detector/confidence/status.
- [ ] Ambiguities are expanded, not collapsed.
- [ ] MEDIUM/LOW claims are marked verification-required.
- [ ] Additional seed validation includes shared/fact/local and fact-vs-fast.
