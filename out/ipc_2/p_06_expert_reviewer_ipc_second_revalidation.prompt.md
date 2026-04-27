# Prompt for Agent: Expert Reviewer (IPC v2 — Second Re-validation Preflight)

Use these baseline files:
- EXPERT_REVIEWER_ROLE_PROMPT.md
- EXPERT_REVIEWER_WORKFLOW.md
- REVIEW_PROMPT_TEMPLATE.md
- REVIEW_PROMPT_PREFLIGHT_EXPERT.md

## Objective

Validate **second-remediation** Expert outputs (d_07, d_08) against d_06 findings and report verdict:
- **READY** → Knowledge Extractor execution gate opened (3 cycles completed successfully)
- **NEEDS_FIX** → Escalation required (issues persist despite 2 remediation attempts)
- **NEEDS_ESCALATION** → Manual intervention (systematic problems detected)

## Inputs

### Re-validation Checklist (from d_06 NEEDS_FIX findings)
- **d_06_expert_reviewer_ipc_revalidation_report.md**: Previous re-validation report identifying 4 specific blockers
- **Remediated adapter**: out/ipc_2/d_07_ipc.adapter.md (NEW, second attempt)
- **Remediated instruction**: out/ipc_2/d_08_knowledge-extractor-ipc.instructions.md (NEW, second attempt)
- **Database**: out/seL4_analysis.db, run_id=1

---

## Review Mode

**Mode**: Preflight Review-Lite (Expert output validation, final gate before KE)
**Scope**: Re-validate d_07 and d_08 against 4 residual blockers from d_06
**Re-review gate**: If any blocker remains unresolved → NEEDS_FIX or NEEDS_ESCALATION

---

## Mandatory Checks (4-Blocker Validation)

### ✅ C2: Local-Seed Over-Filtering (CRITICAL)

**Original d_06 finding**: d_04 over-filtered local seed to 0; broader query shows 22 hits

**Verification in d_07**:
- [ ] d_07 Seeds section: local seed count updated (expect 22, not 0)
- [ ] DB query shown: `SELECT COUNT(*) FROM reference_candidates WHERE run_id=1 AND name LIKE '%local%'` 
- [ ] Result documented: 22 candidates found
- [ ] Confidence downgraded appropriately: MEDIUM-LOW with rationale (e.g., "12 non-call candidates")
- [ ] Query is NOT over-filtered to categorical absence

**Status**: ✅ Fixed | ⚠️ Partially fixed | ❌ Not fixed

---

### ✅ C3: receiveIPC Conditional Formulation (CRITICAL)

**Original d_06 finding**: d_04 claims `CONFIG_KERNEL_MCS=0` but DB shows `ifdef CONFIG_KERNEL_MCS`

**Verification in d_07**:
- [ ] d_07 Representative Functions section: receiveIPC conditional listed
- [ ] Conditional formulation matches DB: should be `ifdef CONFIG_KERNEL_MCS` (not `=0`)
- [ ] Query backing this claim shown: 
  ```sql
  SELECT directive, condition FROM conditional_regions 
  WHERE condition LIKE '%CONFIG_KERNEL_MCS%'
  ```
- [ ] Result aligns with d_07 documentation
- [ ] If =0 interpretation used: separate proof provided and documented

**Alternative check** (if =0 claim retained):
- [ ] Explicit query shown: `SELECT condition FROM conditional_regions WHERE condition LIKE '%=0%'`
- [ ] Rationale documented for why alternative interpretation is preferred

**Status**: ✅ Corrected to ifdef | ✅ Separate proof provided for =0 | ⚠️ Partially addressed | ❌ Still incorrect

---

### ✅ C1: fastpath_call Verification Wording (HIGH)

**Original d_06 finding**: fastpath_call presented as fully verified entity; actually call-site evidence only

**Verification in d_07**:
- [ ] d_07 Representative Functions: fastpath_call confidence rationale explicitly distinguishes call-site evidence
- [ ] Wording avoids overclaiming (e.g., "not presented as entity definition")
- [ ] Query evidence shown: `SELECT invoked_name FROM v_call_in WHERE run_id=1 AND invoked_name='fastpath_call'` (3 rows)
- [ ] Confidence justified: MEDIUM or appropriate for call-graph evidence via cscope
- [ ] Contrast made clear: "observed in v_call_in (call-site evidence) vs defined in entities table (entity evidence)"

**Confidence check**:
- [ ] Is fastpath_call confidence ≤ MEDIUM? (cscope detector caps at MEDIUM per AGENTS.md)
- [ ] Language avoids "verified entity" if not present in entities table?

**Status**: ✅ Clearly distinguished | ⚠️ Mostly clear but wording imprecise | ❌ Still overclaiming

---

### ✅ H3: Confidence Discipline Consistency (HIGH)

**Original d_06 finding**: cscope-derived claims elevated; provenance mixed/inconsistent

**Verification in d_07**:

**Section: Confidence Discipline Rules**
- [ ] Explicit rule present: "cscope detector → MEDIUM confidence maximum"
- [ ] Explicit rule present: "call-site evidence vs entity-definition must be labelled"
- [ ] Explicit rule present: "entities table entry (ctags/tree_sitter) → HIGH possible; v_call_in only → MEDIUM max"
- [ ] Rules are clear and audit-ready

**Per-entry confidence audit** (spot-check at least 5 entries):
- [ ] seL4_ prefix: confidence justified as MEDIUM (detector=cscope via v_call_in)
- [ ] reply_ prefix: confidence justified (detector and evidence clear)
- [ ] At least 3 representative functions: confidence notation includes detector and evidence type
- [ ] No cscope-derived claims presented as HIGH
- [ ] No call-site evidence presented with entity-definition confidence

**Status**: ✅ Consistent discipline applied | ⚠️ Mostly consistent with gaps | ❌ Discipline still violated

---

## Contract Compliance Audit (Rapid Check)

**d_07 Mandatory Fields** (verify all present):
- [ ] Metadata: status field set
- [ ] Scope: conditional presence noted
- [ ] Seeds: corrected with query evidence
- [ ] Entities: primary + supporting (7 total)
- [ ] API: prefixes with detector attribution
- [ ] Representative functions: with confidence per function
- [ ] Confidence Discipline: rules + ambiguity audit documented
- [ ] Lifecycle: documented (if present in d_06)

**d_08 Mandatory Fields**:
- [ ] YAML frontmatter: description, applyTo
- [ ] Adapter binding: points to d_07
- [ ] Usage conditions: adapted to d_07 specifics
- [ ] Output structure: 10 sections
- [ ] Seed validation rule: reflects d_07 corrected counts

**Result**: ✅ All present | ⚠️ Mostly present | ❌ Missing fields

---

## Decision Synthesis

**READY Conditions** (all must be true):
- ✅ C2 fixed: local seed count corrected (22, not 0) with query evidence
- ✅ C3 fixed: receiveIPC conditional correct (ifdef CONFIG_KERNEL_MCS or justified alternative)
- ✅ C1 fixed: fastpath_call wording clear (call-site vs entity)
- ✅ H3 fixed: confidence discipline rules present + applied consistently
- ✅ Contract: all mandatory fields present + non-empty
- ✅ No new blockers discovered

**NEEDS_FIX Conditions** (any one triggers iteration):
- ❌ C2 still not corrected (over-filtered, lacks query evidence, or count still wrong)
- ❌ C3 still incorrect (conditional doesn't match DB or alternative not proven)
- ❌ C1 still overclaiming (fastpath_call presented as entity despite call-site only)
- ❌ H3 still inconsistent (cscope claims elevated, provenance unclear, or discipline violated)
- ❌ Contract mandatory fields empty or vague
- ❌ New blockers discovered (new cycle would be 4th)

**NEEDS_ESCALATION Conditions**:
- ❌ Same blockers persist despite 2 expert remediation cycles
- ❌ New systematic issues discovered (e.g., adapter/KE consumer mismatch at architecture level)
- ❌ Recommendation: Manual user review of d_07 + d_08 before proceeding; or halt and reassess methodology

---

## Output Format

Create report as: **d_09_expert_reviewer_ipc_final_validation_report.md**

```markdown
# Expert Reviewer: IPC v2 Final Validation Report (d_09)

**Mode**: Preflight Review-Lite  
**Status**: READY | NEEDS_FIX | NEEDS_ESCALATION  
**Run Date**: [today]

## Executive Summary
[Verdict + brief findings summary]

## Blocker Fix Verification Summary

### C2: Local-Seed Over-Filtering
- Finding: [what you checked]
- Result: ✅/⚠️/❌
- Evidence: [query + result]
- Verdict: Fixed | Partially fixed | Not fixed

### C3: receiveIPC Conditional
- Finding: [what you checked]
- Result: ✅/⚠️/❌
- Evidence: [DB query backing conditional]
- Verdict: Corrected | Partially corrected | Incorrect

### C1: fastpath_call Wording
- Finding: [what you checked]
- Result: ✅/⚠️/❌
- Evidence: [confidence rationale from d_07]
- Verdict: Clear distinction | Mostly clear | Still overclaiming

### H3: Confidence Discipline
- Finding: [rules present + consistent application]
- Result: ✅/⚠️/❌
- Evidence: [rules excerpt + spot-check examples]
- Verdict: Consistent | Mostly consistent | Still inconsistent

## Contract Compliance Audit
[Table: field → status]

## Final Verdict
**Status**: READY | NEEDS_FIX | NEEDS_ESCALATION
- If READY: KE execution can proceed (d_10 onwards)
- If NEEDS_FIX: Blockers list + specific fixes needed
- If NEEDS_ESCALATION: Recommendation for user action

## Artifacts Traceability
- d_01/d_02 (cycle 1, NEEDS_FIX)
- d_03 (cycle 1 preflight, 10 findings)
- d_04/d_05 (cycle 2 remediation, NEEDS_FIX)
- d_06 (cycle 2 re-validation, NEEDS_FIX)
- d_07/d_08 (cycle 3 remediation, subject of this report)
- d_09 (this report, cycle 3 final validation)
```

---

## Stop Conditions (Review Complete When)

✅ All 4 blockers (C2, C3, C1, H3) evaluated against d_07  
✅ Contract compliance audit finished  
✅ Verdict determined: READY vs NEEDS_FIX vs NEEDS_ESCALATION  
✅ Report saved as d_09_expert_reviewer_ipc_final_validation_report.md

---

## Notes for Reviewer

- This is the **second re-validation**. Use d_06 blocker list as authoritative checklist.
- If all 4 blockers are genuinely fixed → READY (KE gates open).
- If any blocker persists → carefully assess whether it's a new issue or same issue in different form.
- If >2 similar issues in 3 cycles → consider NEEDS_ESCALATION (methodology question, not just fixing).

---

## Deliverables

| Artifact | Type | Purpose |
|----------|------|---------|
| d_09_expert_reviewer_ipc_final_validation_report.md | Report | Final validation + KE gates |

**Next step after your output**:
- If READY → Create p_07 for Knowledge Extractor execution
- If NEEDS_FIX → Create p_05b for Expert 3rd remediation (or escalate)
- If NEEDS_ESCALATION → Halt; recommend user manual review
