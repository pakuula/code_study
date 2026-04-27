---
description: "Updated IPC knowledge extractor instruction (v4). Bind to d_07 and produce Layer A + Layer B outputs with evidence and confidence discipline."
applyTo: "out/ipc_2/*.md"
---

# Knowledge Extractor Instruction: IPC (Remediated v4)

## Usage Conditions

Use this instruction only for IPC extraction tasks that:
- use DB out/seL4_analysis.db
- are scoped to run_id=1
- bind to out/ipc_2/d_07_ipc.adapter.md
- require detector-aware confidence handling
- follow KE/Synthesizer boundary contract

If d_07 is missing, stop and request corrected inputs.

## Required Adapter Binding

1. Load out/ipc_2/d_07_ipc.adapter.md before running extraction queries.
2. Ignore d_01 and d_04 as authoritative sources for current cycle decisions.
3. Inherit d_07 fields for:
   - entity pool and representative functions
   - prefix families
   - conditional presence wording
   - confidence provenance rules
4. Follow KE role and workflow contracts:
  - KNOWLEDGE_EXTRACTOR_ROLE_PROMPT.md
  - KNOWLEDGE_EXTRACTOR_WORKFLOW_ALGORITHM.md
5. Respect KE_SYSTEM_SYNTHESIZER_BOUNDARY.md:
  - produce Layer A and Layer B outputs
  - do not replace Layer C synthesis role

## Required Output Structure (13 Sections)

1. Metadata (source_adapter=d_07, run_id, db_path, status)
2. Scope (including receiveIPC conditional note)
3. Core Entities
4. Supporting Types
5. API Surface
6. Representative Workflows
7. Variants and Mode Markers
8. Lifecycle
9. Exclusions Applied
10. Subsystem Overview (implementation-semantic)
11. Client Use Cases (evidence-backed)
12. Confidence and Ambiguity Notes
13. Verification TODOs

Minimum fields per factual item:
- claim
- source_view_or_table
- detector
- confidence
- status (observed or inferred)

Minimum fields per use case:
- use_case_id
- title
- caller_evidence
- callee_or_api_family
- implementation_goal
- conditions_or_variants
- status (observed or inferred)
- detector
- confidence
- verification_note (required for MEDIUM/LOW semantics)

## Seed Validation Rules (Bound to d_07)

- shared:
  - classification: NOT_FOUND_IN_CURRENT_INDEX
  - query:
    SELECT COUNT(*) FROM reference_candidates
    WHERE run_id=1 AND name LIKE '%shared%';
  - expected_result: 0

- fastpath:
  - classification: CONFIRMED_IPC_ADJACENT_VARIANT
  - query:
    SELECT COUNT(*) FROM v_call_in
    WHERE run_id=1 AND invoked_name LIKE 'fastpath_%';
  - expected_result: 6
  - confidence_cap: MEDIUM

- local:
  - classification: PRESENT_BUT_LOW_DOMAIN_SPECIFICITY
  - query:
    SELECT COUNT(*) FROM reference_candidates
    WHERE run_id=1 AND name LIKE '%local%';
  - expected_result: 22
  - decomposition query:
    SELECT candidate_type, access_kind, COUNT(*)
    FROM reference_candidates
    WHERE run_id=1 AND name LIKE '%local%'
    GROUP BY candidate_type, access_kind;
  - expected_decomposition:
    - call_candidate/call=12
    - read_write_candidate/read=10
  - confidence_note: MEDIUM-LOW domain relevance

## Representative Function Rules (Bound to d_07)

- receiveIPC:
  - conditional format must be exactly: ifdef CONFIG_KERNEL_MCS
  - backing query class: entity_presence_conditions joined to conditional_regions

- fastpath_call:
  - must be labeled call-site evidence only
  - required dual-check:
    - v_call_in count query (expected 3)
    - entities existence query (expected 0)
  - confidence cap: MEDIUM
  - prohibited wording: verified entity definition

## Subsystem Overview and Use-Case Rules

- Subsystem Overview must stay implementation-semantic:
  - what exists
  - how components interact
  - where constraints/variants apply
- Do not present policy-level or organization-level intent as observed fact.

Use-case derivation evidence baseline:
- v_call_in for caller/callee patterns
- v_type_uses for entity/type participation in scenarios
- representative workflows for step ordering context

Use-case reporting rules:
- each use case must be labeled observed or inferred
- each decisive statement must carry detector/confidence provenance
- use-case narratives must not contradict core entity or API evidence

## Confidence Provenance Rules (Inherited from d_07)

1. cscope evidence (v_call_in, call_candidate) has MEDIUM maximum confidence.
2. ctags/tree_sitter entity-definition evidence can be HIGH.
3. Call-site vs entity-definition evidence classes must be labeled explicitly.
4. If symbol exists only in v_call_in and not in entities, do not claim HIGH.
5. When behavior is inferred from MEDIUM/LOW evidence, label as index-derived and verification-required.

## Adapter Binding Checklist (d_07)

- [ ] d_07_ipc.adapter.md loaded.
- [ ] run_id=1 applied to all SQL.
- [ ] local seed shown as 22 with decomposition 12/10.
- [ ] receiveIPC conditional rendered as ifdef CONFIG_KERNEL_MCS.
- [ ] fastpath_call described as call-site evidence only.
- [ ] confidence caps follow provenance rules.
- [ ] no unsupported CONFIG_KERNEL_MCS=0 claim appears.

## KE and Synthesizer Boundary Checklist

- [ ] Output includes Layer A (facts) and Layer B (use cases).
- [ ] Output does not substitute Layer C synthesis role.
- [ ] Any high-level interpretation beyond direct evidence is marked inferred and verification-required.

## Output Verification Against d_07

Before final output, verify:
- metadata status aligns with d_07 status READY
- representative functions match d_07 list
- API prefix confidence remains MEDIUM for v_call_in-sourced claims
- conditional statements are backed by entity-linked conditional query
- subsystem overview uses implementation-level language
- use cases are backed by call/type/workflow evidence and status labels

## Runtime Notes

- d_07 resolves C2/C3/C1/H3 blockers from d_06.
- Continue to treat DB as heuristic index, not compiler truth.
- If ambiguity_group_id appears for IPC entities in future runs, list all candidates explicitly.
- After KE output is produced, run full KE review prompt (p_08) before synthesis stage.
