# Prompt for Agent: Expert (IPC v2 — Remediation Cycle)

Use these baseline files:
- EXPERT_ROLE_PROMPT.md
- EXPERT_WORKFLOW_ALGORITHM.md
- FEATURE_EXTRACTION_GUIDE.md
- EXPERT_ADAPTER_METHOD.md

## Objective

Based on Expert Reviewer preflight findings (d_03), create **remediated and verified** adapter and KE instruction artifacts for Knowledge Extractor deployment.

**Critical constraint**: Create NEW artifacts (d_04, d_05), do NOT modify existing d_01, d_02. Maintain version traceability.

Do not generate an IPC feature report. Do not execute Knowledge Extractor in this task.

---

## Inputs

### Primary Inputs
- **Preflight report**: out/ipc_2/d_03_expert_reviewer_ipc_preflight_report.md
  - 10 findings (3 CRITICAL, 3 HIGH, 3 MEDIUM, 1 LOW)
  - 4 CRITICAL blockers must be fixed before re-validation
  - 2 HIGH scope/contract issues must be resolved
- **Database**: out/seL4_analysis.db, run_id=1
- **Previous adapter (reference)**: out/ipc_2/d_01_ipc.adapter.md
- **Previous instruction (reference)**: out/ipc_2/d_02_knowledge-extractor-ipc.instructions.md

### Mandatory Blockers to Fix (from d_03)

**CRITICAL issues**:

1. **C1: `fastpath_call` not verified**
   - Finding: Not a real entity in DB (query returned 0 rows)
   - Action: Either replace with verified fastpath-related entity from v_call_in, or document as hypothetical pattern
   - Verification: Run query against DB before finalizing

2. **C2: Seed validation evidence count mismatches**
   - Findings:
     - "shared" claimed 16, actual 7
     - "fastpath" (fast) claimed 19, actual 6
     - "local" claimed 27, actual 4
   - Action: Re-run DB queries; use TRUE counts; downgrade confidence to MEDIUM or LOW with verification notes
   - Verification: Each count must be backed by exact SQL query in confidence notes

3. **C3: `receiveIPC` CONFIG_KERNEL_MCS conditional not documented**
   - Finding: Entity presence conditional on `CONFIG_KERNEL_MCS=0` not mentioned
   - Action: Add conditional_presence note in entities section; explain availability restriction
   - Verification: Confirm via entity_presence_conditions table query

4. **C4: `seL4_IPCBuffer` evidence unverified**
   - Finding: Evidence sum (3+1+1=5) doesn't match actual DB count (~15)
   - Action: Re-query v_type_uses; correct counts; document score methodology
   - Verification: Execute query; document findings

**HIGH issues** (scope/contract):

5. **H2: API prefix evidence filtering vague**
   - Finding: "IPC-filtered token frequency" undefined; no detector info
   - Action: Replace with exact DB query + result counts; add per-prefix detector/confidence
   - Verification: Query v_call_in or v_type_uses; document exact methodology

6. **H3: Confidence notes incomplete**
   - Finding: Detector attribution missing; confidence discipline not documented
   - Action: Add per-entity detector source + confidence rationale; check ambiguity_group conflicts
   - Verification: Link each confidence rating to detector + evidence source

---

## Required Outputs

Create two **new** artifacts under out/ipc_2 (do NOT overwrite d_01, d_02):

### 1. out/ipc_2/d_04_ipc.adapter.md

**Specification**:
- Metadata section: all fields from d_01 plus `status: READY` (only if all blockers fixed and validated)
- Scope: refined from d_01; document conditional presence (receiveIPC)
- Seeds: corrected with TRUE DB counts + downgraded confidence + verification queries shown
- Entities (primary): replace fastpath_call with verified entity (or remove); add conditional_presence note for receiveIPC
- Entities (supporting): corrected seL4_IPCBuffer evidence with DB-backed counts
- API: detailed prefix evidence with exact query results + detector attribution per prefix
- Confidence discipline: new section explaining detector sources + ambiguity_group audit results
- Lifecycle: if unchanged from d_01, state clearly; otherwise add enumerations with evidence
- Representative functions: add file:line numbers, detector, confidence per function

**Validation checklist**:
- [ ] All C1–C4 blockers addressed with DB-backed evidence
- [ ] Seed counts verified via SQL queries (show query + result in confidence notes)
- [ ] fastpath_call replaced or caveat added
- [ ] receiveIPC CONFIG_KERNEL_MCS documented
- [ ] seL4_IPCBuffer evidence corrected
- [ ] API prefix methodology transparent (query-based, not intuition)
- [ ] Detector attribution per entity (tree_sitter vs ctags vs cscope vs reconcile)
- [ ] Ambiguity audit results documented
- [ ] YAML frontmatter added (description, applyTo, etc.)
- [ ] No CRITICAL/HIGH findings remain

### 2. out/ipc_2/d_05_knowledge-extractor-ipc.instructions.md

**Specification**:
- Update to bind against d_04 (not d_01)
- Inherit metadata from d_04 (run_id, db_path, detector attribution)
- Keep all sections from d_02 but ensure:
  - Adapter binding section now points to d_04_ipc.adapter.md
  - Additional seed validation rule reflects corrected seed counts from d_04
  - Confidence discipline in output structure rules now references d_04 detector/ambiguity findings
  - Any d_01 assumptions about fastpath_call or seL4_IPCBuffer updated to match d_04

**YAML frontmatter**:
```yaml
---
description: "Updated IPC knowledge extractor instruction (v2 remediated). Use with d_04_ipc.adapter.md."
applyTo: "out/ipc_2/*.md"
---
```

**Validation checklist**:
- [ ] Adapter binding points to d_04
- [ ] All seeds reference d_04 corrected counts
- [ ] fastpath_call references updated or removed
- [ ] seL4_IPCBuffer references updated with corrected evidence
- [ ] Output structure documentation matches d_04 entity list
- [ ] Confidence rules inherit d_04 detector + ambiguity discipline

---

## Scope Rules

- **DB is the source of truth**: All claims must be DB-backed via SQL queries shown in artifact or confidence notes
- **No hallucination**: If entity/function not in DB, document as "hypothetical pattern" or remove
- **Confidence discipline**: Downgrade to MEDIUM or LOW if only one detector found; explain in notes
- **Conditional presence**: Mark all entities/functions subject to CONFIG_* or architecture filters
- **Ambiguity audit**: Explicitly document any ambiguity_group_id entries; list all candidates
- **No overwrites**: Create d_04, d_05 as new files; d_01, d_02 remain for audit trail

---

## Handoff Contract Target (for d_04, d_05)

Your artifacts must satisfy Knowledge Extractor consumer contract:

**Mandatory fields in d_04**:
- ✅ Metadata (feature_label, db_path, run_id, status)
- ✅ Entities: primary + supporting, each with detector + confidence + conditional_presence
- ✅ API anchors: prefixes with exact evidence methodology + detector per prefix
- ✅ Representative functions: with file:line, detector, confidence
- ✅ Confidence notes: detector source per entity + ambiguity_group audit results
- ✅ Ambiguity notes: all ambiguity_group_id findings + rationale for candidate choice (or "list all")

**Mandatory fields in d_05**:
- ✅ Adapter binding: explicit reference to d_04
- ✅ Output structure: 10 sections with minimum per-item fields (claim, source, detector, confidence)
- ✅ Seed validation: corrected counts from d_04

---

## Quality Gates

**Before declaring status=READY in d_04**:

1. **All CRITICAL fixes verified** (C1–C4)
   - Run each query yourself; show results in confidence notes
   - If count differs from claim, explain or downgrade confidence

2. **Contract compliance confirmed** (all mandatory fields present + non-empty)
   - Use d_03 table: all ✅ or ⚠️ resolved to ✅

3. **No unresolved ambiguity**
   - If ambiguity_group_id entries exist, list all candidates + rationale

4. **Confidence discipline observed**
   - HIGH confidence only if 2+ detectors agree OR high-confidence detector (ctags, tree_sitter)
   - MEDIUM/LOW confidence explicitly marked with verification_required note

---

## Execution Notes

- Load d_03 preflight report first; use it as your specification
- For each blocker (C1–C4, H2, H3), add a new subsection in d_04 explaining fix + evidence
- Keep d_01/d_02 immutable for audit trail; newer versions are d_04/d_05
- If you discover NEW issues while fixing, document them in d_04 Confidence notes
- Query v_call_in, v_type_uses, entity_presence_conditions, ambiguity_groups tables directly; show SQL in artifact

---

## Deliverables Summary

| Artifact | Type | Purpose | Input |
|----------|------|---------|-------|
| d_04_ipc.adapter.md | Adapter | Remediated domain bindings | d_03 findings |
| d_05_knowledge-extractor-ipc.instructions.md | Instruction | Updated consumer contract | d_04 |

**Next step after your output**: Expert Reviewer will run preflight on d_04 + d_05 (p_04).
If verdict is READY → Knowledge Extractor execution can begin.
