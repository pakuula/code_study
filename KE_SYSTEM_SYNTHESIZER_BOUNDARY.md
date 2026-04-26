# KE and System Synthesizer Boundary Contract

Purpose: define a strict separation between evidence extraction and high-level semantic synthesis.

## Role Split

### Layer A: KE Observed Facts
Owner: Knowledge Extractor

Produces:
- query-backed entities, API surfaces, workflows, variants
- evidence tables and claim-level provenance
- confidence and ambiguity notes

Constraints:
- no unsupported semantic intent claims
- explicit observed vs inferred markers
- run_id-scoped evidence only

### Layer B: KE Evidence-Backed Use Cases
Owner: Knowledge Extractor

Produces:
- client use-case patterns derived from call and type evidence
- scenario descriptions with detector/confidence provenance
- verification TODOs for MEDIUM/LOW behavior claims

Constraints:
- implementation-semantic level only
- no policy-level or product-level intent assertions as fact

### Layer C: System Semantic Synthesis
Owner: System Synthesizer

Produces:
- subsystem overview narrative
- use-case family consolidation
- high-level semantic interpretation and trade-offs
- architecture-facing summary with uncertainty ledger

Constraints:
- must trace back to KE evidence
- inferred statements explicitly labeled
- no hidden confidence elevation

## Handoff Contract

KE -> System Synthesizer mandatory package:
- KE report path
- adapter path
- instruction path
- db_path
- run_id
- confidence and ambiguity section references
- unresolved TODO list

System Synthesizer -> downstream docs/review package:
- synthesis report path
- synthesis confidence ledger
- unresolved ambiguity list
- verification TODO list

## Disallowed Overlap

KE must not:
- claim architecture intent beyond evidence class
- produce policy-level rationale as fact

System Synthesizer must not:
- rerun full extraction and replace KE output
- output review verdicts (PASS/FAIL/READY)

## Escalation Rules

Escalate to Expert Reviewer when:
- synthesis appears to overclaim beyond KE evidence
- ambiguity is collapsed without alternatives
- confidence labels are missing or inconsistent

Escalate to Expert when:
- adapter scope is insufficient for requested synthesis
- key use-case families require new extraction coverage
