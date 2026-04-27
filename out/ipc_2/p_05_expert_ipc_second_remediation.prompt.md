# Prompt for Agent: Expert (IPC v2 — Second Remediation Cycle)

Use these baseline files:
- EXPERT_ROLE_PROMPT.md
- EXPERT_WORKFLOW_ALGORITHM.md
- FEATURE_EXTRACTION_GUIDE.md
- EXPERT_ADAPTER_METHOD.md

## Objective

Address residual blockers identified in Expert Reviewer re-validation report (d_06).

**Cycle 2 produced d_04/d_05 with verdict NEEDS_FIX**. You must now fix the 4 residual issues and create **new** artifacts d_07, d_08 (third cycle), maintaining traceability.

Do not modify d_04, d_05. Create d_07, d_08 as fresh remediated versions.

---

## Inputs

### Re-validation Report
- **d_06_expert_reviewer_ipc_revalidation_report.md**: NEEDS_FIX verdict with 4 specific blocker assessments

### Specific Blockers to Fix (from d_06)

#### BLOCKING ISSUE 1: C2 Local-Seed Over-Filtering
**Problem**: d_04 uses overly narrow filter and reports local-seed as categorical absence (0).  
**D_06 Evidence**: Broader query shows 22 hits for `name LIKE '%local%'`
```sql
SELECT candidate_type, access_kind, COUNT(*) FROM reference_candidates 
WHERE run_id = 1 AND name LIKE '%local%' 
GROUP BY candidate_type, access_kind
→ call_candidate/call: 12, read_write_candidate/read: 10
```
**Fix Required**: 
- Replace narrow filter with transparent, auditable query (not over-filtered to 0)
- Document exact SQL query used
- Present true count (22) with confidence assessment
- Rationale: "local" seed exists in DB but with lower relevance to IPC domain (12 of 22 are non-call-context)

#### BLOCKING ISSUE 2: C3 receiveIPC Conditional Formulation
**Problem**: d_04 claims `CONFIG_KERNEL_MCS=0` but DB evidence shows `ifdef CONFIG_KERNEL_MCS` (no =0 suffix).  
**D_06 Evidence**:
```sql
SELECT directive, condition FROM conditional_regions 
WHERE condition LIKE '%CONFIG_KERNEL_MCS%'
→ directive: ifdef, condition: CONFIG_KERNEL_MCS (no =0)

SELECT condition FROM conditional_regions WHERE condition LIKE '%=0%'
→ No rows matching
```
**Fix Required**:
- Change d_07 conditional statement to match DB: `ifdef CONFIG_KERNEL_MCS` (not `=0`)
- OR provide separate proof/query showing why `=0` interpretation is correct
- Document exact conditional query backing the claim
- Rationale: Precision matters for KE scope determination

#### PARTIAL ISSUE 3: C1 fastpath_call Verification Wording
**Problem**: d_04 presents fastpath_call as fully verified entity, but it's call-site evidence only (not in entities table).  
**D_06 Evidence**:
```sql
SELECT invoked_name FROM v_call_in WHERE run_id=1 AND invoked_name='fastpath_call'
→ 3 rows (call-graph backed)

SELECT name FROM entities WHERE run_id=1 AND name='fastpath_call'
→ No entity row
```
**Fix Required**:
- Clarify in d_07 that fastpath_call has call-graph evidence but no entity-table record
- Update confidence rationale: explain why call-site evidence is sufficient (or not)
- Distinguish clearly: "observed in v_call_in (MEDIUM confidence via cscope)" vs "defined as entity (would be HIGH via ctags)"
- Update representative_functions wording to avoid overclaiming

#### PARTIAL ISSUE 4: H3 Confidence Discipline Inconsistency
**Problem**: cscope-derived claims sometimes presented stronger than detector rules justify. Mixed provenance between call-graph and definition evidence.  
**D_06 Evidence**: "cscope-derived claims are sometimes elevated" and "fastpath_call framing too strong"  

**Fix Required**:
- Add explicit confidence provenance rules to d_07 Confidence Discipline section
- Rule: cscope detector → MEDIUM confidence maximum (per AGENTS.md)
- Rule: call-site evidence vs entity-definition evidence must be clearly labelled
- Rule: If entity exists in `entities` table → can claim HIGH; if only in v_call_in → MEDIUM max
- Audit all entries in d_07 API section and representative_functions against this rule
- Update d_08 instruction to reflect this discipline

---

## Required Outputs

Create two **new** artifacts under out/ipc_2 (do NOT modify d_04, d_05):

### 1. out/ipc_2/d_07_ipc.adapter.md

**Changes from d_04 → d_07**:

**Section: Seeds (C2 fix)**
- local seed: Replace 0 (over-filtered) with true count (22)
- Query shown: `SELECT COUNT(*) FROM reference_candidates WHERE run_id=1 AND name LIKE '%local%'` → 22
- Confidence: MEDIUM-LOW with note "22 hits include 12 non-call candidates; IPC relevance unclear"
- Keep shared seed as NOT_FOUND (correct)
- Keep fastpath seed as MEDIUM with 6 count (correct)

**Section: Representative Functions (C1 + H3 fixes)**
- receiveIPC: Change conditional from `CONFIG_KERNEL_MCS=0` to `ifdef CONFIG_KERNEL_MCS`
- Query backing conditional: Show exact query result from conditional_regions
- fastpath_call: Update confidence rationale to clearly note "call-graph evidence (v_call_in), no entity record"
- Per-function confidence: Ensure each matches detector (entity-def vs call-site only)

**Section: Confidence Discipline (H3 fix)**
- Add explicit "Confidence Provenance Rules":
  - cscope (v_call_in) → MEDIUM max
  - ctags or tree_sitter (entities table) → HIGH possible
  - call-site vs definition distinction → must be labelled clearly
- Audit each API prefix and representative function against these rules
- Update confidence levels if necessary (may downgrade some to match detector limits)

**Section: Additional Notes**
- Acknowledge that third-cycle remediation was necessary
- Document rationale for each fix (why cycle 2 was incomplete)
- Note any residual risks discovered during this cycle

**Metadata**:
- status: READY (only if all 4 blockers truly fixed)
- remediation_cycle: 3
- remediation_date: 2026-04-26

### 2. out/ipc_2/d_08_knowledge-extractor-ipc.instructions.md

Update to bind against d_07 (not d_04):
- Adapter binding section → points to d_07
- Seeds section → reflects d_07 corrected local seed count (22)
- Confidence discipline rules → inherit explicit provenance rules from d_07
- Representative functions section → references d_07 corrected fastpath_call and receiveIPC
- YAML frontmatter: updated to reference d_07

---

## Quality Gates

**Before declaring status=READY in d_07**:

1. **C2 fix verified**: true local seed count (22) backed by query, confidence appropriately assigned
2. **C3 fix verified**: receiveIPC conditional matches DB directive/condition format exactly (ifdef CONFIG_KERNEL_MCS)
3. **C1 fix verified**: fastpath_call confidence rationale clearly distinguishes call-site evidence
4. **H3 fix verified**: All confidence claims match detector provenance (cscope → MEDIUM max, etc.)

**Contract compliance**: All mandatory fields non-empty, no vague language

---

## Execution Notes

- D_06 analysis is authoritative; use its specific SQL queries as starting point
- For each fix, show the DB query that validates it
- If you discover why cycle 2 was incomplete, document in d_07 Additional Notes
- If new issues emerge during this cycle, document them but don't delay status=READY if main 4 blockers are fixed

---

## Deliverables Summary

| Artifact | Purpose | Input |
|----------|---------|-------|
| d_07_ipc.adapter.md | Remediated adapter (3rd cycle, final) | d_06 findings |
| d_08_knowledge-extractor-ipc.instructions.md | Updated consumer contract (3rd cycle) | d_07 |

**Next phase**: Expert Reviewer will run preflight on d_07 + d_08 (p_06).
If verdict = READY → Knowledge Extractor execution.
If verdict = NEEDS_FIX → escalation (likely 4th cycle or manual intervention).
