# Prompt for Agent: Expert Reviewer (IPC v2 — Re-validation Preflight)

Use these baseline files:
- EXPERT_REVIEWER_ROLE_PROMPT.md
- EXPERT_REVIEWER_WORKFLOW.md
- REVIEW_PROMPT_TEMPLATE.md
- REVIEW_PROMPT_PREFLIGHT_EXPERT.md

## Objective

Validate **remediated** Expert outputs (d_04, d_05) against preflight acceptance criteria and report verdict:
- **READY** → Knowledge Extractor execution gate opened
- **NEEDS_FIX** → Additional remediation cycle required (or escalation)

## Inputs

### Primary Inputs
- **Previous preflight report** (for reference, NOT authority): out/ipc_2/d_03_expert_reviewer_ipc_preflight_report.md
  - 10 findings: 4 CRITICAL, 2 HIGH, 3 MEDIUM, 1 LOW
  - 6 blocker fixes required
- **Remediated adapter**: out/ipc_2/d_04_ipc.adapter.md (NEW)
- **Remediated instruction**: out/ipc_2/d_05_knowledge-extractor-ipc.instructions.md (NEW)
- **Database (evidence source)**: out/seL4_analysis.db, run_id=1

### Context for Interpretation
- Previous iteration: d_01 + d_02 failed blockers C1–C4, H2, H3 (documented in d_03)
- Expert task: p_03 required to produce d_04, d_05 with fixes
- Goal: Determine if remediation complete and ready for Knowledge Extractor

---

## Review Mode

**Mode**: Preflight Review-Lite (Expert output validation)
**Scope**: Re-validate d_04 and d_05 against 10 d_03 findings
**Re-review gate**: If any CRITICAL finding remains unresolved → status NEEDS_FIX (cycle again)

---

## Mandatory Checks (Preflight Template)

### ✅ Contract Compliance Audit

**Check**: Do d_04 and d_05 satisfy Knowledge Extractor consumer handoff contract?

**Verify in d_04**:
- [ ] Metadata section: feature_label, db_path, run_id, status field present
- [ ] Entities section: primary + supporting, each entry has detector + confidence documented
- [ ] API section: prefixes with evidence methodology + detector per prefix
- [ ] Representative functions: file:line numbers + detector + confidence per function
- [ ] Confidence notes: per-entity detector source + confidence rationale (not just confidence=HIGH)
- [ ] Ambiguity notes: ambiguity_group audit results documented (or "none found")
- [ ] Conditional presence: CONFIG_* and arch-specific availability documented for affected entities

**Verify in d_05**:
- [ ] YAML frontmatter: description, applyTo present
- [ ] Adapter binding section: points to d_04 (not d_01)
- [ ] Usage conditions: adapted to d_04 specifics
- [ ] Output structure: 10 sections with per-item minimum fields (claim, source_view, detector, confidence, status)
- [ ] Seed validation rule: reflects d_04 corrected seed counts

**Verdict**: PASS or FAIL contract compliance

---

### ✅ Evidence Traceability Audit (d_03 Blockers Re-check)

For each of 6 blocker fixes (C1–C4, H2, H3), verify:

#### CRITICAL 1: `fastpath_call` Replacement

**Original finding**: Not a real entity in DB
**Expected fix**: Entity replaced with verified entity, OR caveat added + query shown

**Verification**:
- [ ] If replaced: Does d_04 list new entity? Does it appear in v_call_in (run_id=1)?
  ```sql
  -- Query to verify replacement entity exists
  SELECT invoked_name FROM v_call_in 
  WHERE run_id = 1 AND invoked_name LIKE 'fastpath%'
  LIMIT 5;
  ```
- [ ] If caveat: Does d_04 explicitly note "hypothetical pattern" or "not DB-backed"?
- [ ] No reference to `fastpath_call` remains in d_04 or d_05

**Status**: ✅ Fixed | ⚠️ Partially addressed | ❌ Not addressed

---

#### CRITICAL 2: Seed Evidence Count Corrections

**Original findings**:
- "shared" claimed 16, actual 7
- "fastpath" (fast) claimed 19, actual 6
- "local" claimed 27, actual 4

**Expected fix**: True counts documented + confidence downgraded to MEDIUM or LOW + query shown

**Verification per seed**:

1. **shared seed**:
   - [ ] d_04 claims corrected count (expect ~7, not 16)
   - [ ] Confidence downgraded or rationale given
   - [ ] Query provided in Confidence notes? (expected: `SELECT COUNT(*) FROM reference_candidates WHERE run_id=1 AND name LIKE '%shared%'`)

2. **fastpath seed**:
   - [ ] d_04 claims corrected count (expect ~6, not 19)
   - [ ] If counts still differ, does d_04 explain why? (e.g., "includes macro-expanded variants")
   - [ ] Confidence discipline observed?

3. **local seed**:
   - [ ] d_04 claims corrected count (expect ~4, not 27)
   - [ ] Confidence downgraded to LOW or MEDIUM?
   - [ ] Verification query shown?

**Status**: ✅ All corrected | ⚠️ Partial corrections | ❌ Not corrected

---

#### CRITICAL 3: `receiveIPC` CONFIG_KERNEL_MCS Conditional

**Original finding**: Conditional presence not documented
**Expected fix**: d_04 Entities section includes conditional_presence note for receiveIPC

**Verification**:
- [ ] d_04 mentions receiveIPC (either in primary or supporting entities)
- [ ] If present: Note states "available only when CONFIG_KERNEL_MCS=0" (or similar)
- [ ] Query backup in Confidence notes? (expected: entity_presence_conditions table query)

**Status**: ✅ Documented | ⚠️ Partially documented | ❌ Not addressed

---

#### CRITICAL 4: `seL4_IPCBuffer` Evidence Verification

**Original finding**: Evidence counts (5 total) don't match DB (~15)
**Expected fix**: d_04 lists corrected evidence counts + score methodology documented

**Verification**:
- [ ] d_04 Supporting entities section: seL4_IPCBuffer evidence counts updated (expect ~15 or explanation why different)
- [ ] Score methodology documented? (how is score=4 calculated?)
- [ ] Query verification in Confidence notes? (expected: `SELECT COUNT(*) FROM v_type_uses WHERE run_id=1 AND type_name='seL4_IPCBuffer'`)

**Status**: ✅ Corrected | ⚠️ Partial | ❌ Not corrected

---

#### HIGH 2: API Prefix Filtering Methodology

**Original finding**: "IPC-filtered token frequency" vague; no detector info
**Expected fix**: d_04 API section documents exact query methodology + detector per prefix + result counts

**Verification per prefix** (spot-check at least 3):
- [ ] seL4_ prefix: method documented (e.g., "query v_call_in WHERE invoked_name LIKE 'seL4_%'")
- [ ] fastpath_ prefix: detector attributed (ctags? tree_sitter? v_call_in confidence=HIGH?)
- [ ] reply_ prefix: result count shown (e.g., "9 matches in v_call_in, confidence=HIGH")
- [ ] Evidence phrases are specific, not vague ("IPC-filtered" is gone)

**Status**: ✅ Transparent | ⚠️ Partially transparent | ❌ Still vague

---

#### HIGH 3: Confidence Notes Discipline

**Original finding**: Detector attribution missing; confidence discipline violated
**Expected fix**: d_04 Confidence notes section explains per-entity detector source + ambiguity_group audit

**Verification**:
- [ ] Each primary entity has detector documented (tree_sitter vs ctags vs cscope vs reconcile)
- [ ] Confidence rationale tied to detector (e.g., "HIGH: tree_sitter + ctags agreement")
- [ ] Ambiguity_group audit results documented (e.g., "0 conflicts found" or "3 candidates in group X")
- [ ] If HIGH claimed but only one detector: is it high-confidence detector? (tree_sitter/ctags YES, cscope/regex NO)
- [ ] Any MEDIUM/LOW marked with verification_required note

**Status**: ✅ Disciplined | ⚠️ Mostly disciplined | ❌ Discipline gaps remain

---

### ✅ Scope Drift Audit

**Check**: Did Expert introduce new content outside IPC domain or create new blockers?

**Verify**:
- [ ] d_04 Seeds section: no new seeds added beyond d_01 baseline (or if added, fully verified)
- [ ] d_04 Entities: no new entities without DB backing
- [ ] d_04 API prefixes: no new prefixes without evidence
- [ ] d_05 Output structure: matches d_04 entities (no references to non-existent entities)
- [ ] d_05 Seed validation rule: consistent with d_04

**Red flags**:
- ❌ New seeds claimed without counts
- ❌ New entities with confidence=HIGH but single detector
- ❌ References to entities that don't appear in d_03 or d_01 analysis

**Status**: ✅ No scope drift | ⚠️ Minor additions (acceptable) | ❌ Significant scope changes

---

### ✅ Ambiguity Audit

**Check**: Did Expert document ambiguity_group findings?

**Verify**:
- [ ] d_04 includes explicit "Ambiguity audit results" section
- [ ] If ambiguity_group_id entries found: all candidates listed + selection rationale given
- [ ] If no ambiguities: explicitly states "no ambiguity_group conflicts found in seL4_analysis.db for IPC entities"

**Query verification** (spot-check):
```sql
-- Check for ambiguous IPC entities
SELECT ag.description, e.name, e.detector, e.confidence
FROM entities e
JOIN ambiguity_groups ag ON e.ambiguity_group_id = ag.group_id
WHERE e.ambiguity_group_id IS NOT NULL
  AND e.name IN ('endpoint', 'notification', 'reply', 'message', 'ipc', 'send', 'recv');
```

**Status**: ✅ Documented | ⚠️ Partially documented | ❌ Missing

---

## Decision Synthesis

**READY Conditions** (all must be true):
- ✅ Contract compliance: all mandatory fields present and non-empty
- ✅ CRITICAL fixes: C1–C4 addressed with DB-backed evidence
- ✅ HIGH fixes: H2–H3 resolved (methodology transparent, confidence disciplined)
- ✅ Confidence discipline: no HIGH claimed without strong detector basis
- ✅ No scope drift: d_04/d_05 consistent with IPC domain
- ✅ Ambiguity audit: results documented

**NEEDS_FIX Conditions** (any one triggers re-iteration):
- ❌ Any CRITICAL finding remains unresolved or inadequately addressed
- ❌ Confidence discipline violated (e.g., HIGH claimed for single low-confidence detector)
- ❌ Contract mandatory fields empty or vague
- ❌ New blockers discovered during re-validation
- ❌ Evidence counts still don't match DB after Expert correction

---

## Output Format

### Report Structure

```
# Expert Reviewer: IPC v2 Re-validation Report (d_06)

**Mode**: Preflight Review-Lite
**Status**: READY | NEEDS_FIX | NEEDS_ESCALATION
**Run Date**: [today]

## Executive Summary
[1-2 paragraphs: verdict + key findings]

## Blocker Fix Verification (C1–C4, H2, H3)
[Per-blocker subsections with verification results + status]

## Contract Compliance Audit
[Table: field → status (✅/⚠️/❌)]

## Confidence Discipline Assessment
[Findings: violations or confirmations]

## Scope Drift Audit
[Pass/flag assessment]

## Ambiguity Audit
[Results: documented or findings]

## Re-validation Verdict
- **Status**: READY | NEEDS_FIX
- **Blocking issues** (if NEEDS_FIX): [list specific fixes required]
- **Residual risks** (if READY): [known limitations or MEDIUM/LOW confidence areas]
- **Next gate**: Knowledge Extractor execution (if READY) or p_03 re-iteration (if NEEDS_FIX)

## Artifacts Traceability
- d_01 (original) → deprecated
- d_02 (original) → deprecated
- d_03 (preflight report, 10 findings) → input to this review
- d_04 (remediated adapter) → subject of this review
- d_05 (remediated instruction) → subject of this review
- d_06 (this re-validation report) → audit trail

---
```

### Required Findings Elements

**For each finding/issue**:
- Location (d_04/d_05 section)
- Finding statement (what you checked)
- Result (✅/⚠️/❌)
- Evidence (DB query result or citation)
- Rationale (why this matters)

---

## Stop Conditions (Review Complete When)

✅ All 6 blockers (C1–C4, H2, H3) evaluated
✅ Contract compliance audit finished (all fields checked)
✅ Confidence discipline assessed across all primary entities
✅ Scope drift audit completed
✅ Ambiguity audit documented
✅ Verdict determined: READY vs NEEDS_FIX vs NEEDS_ESCALATION
✅ Report saved as d_06_expert_reviewer_ipc_revalidation_report.md

---

## Escalation Criteria

If any of these apply → NEEDS_ESCALATION verdict (notify user for guidance):

- ❌ Expert created d_04/d_05 but they still contain obvious hallucinations (entities not in DB, unverifiable queries)
- ❌ All 4 CRITICAL blockers remain unresolved despite p_03 iteration
- ❌ New findings discovered that suggest adapter scope is too broad or too narrow
- ❌ Evidence discipline still violated in majority of entities (>50% confidence ratings unjustified)

**If NEEDS_ESCALATION**: Recommend user review d_03 + d_04 + d_05 manually before proceeding.

---

## Notes for Reviewer

- This is a **re-validation**, not a full review. Use d_03 as your checklist of known issues.
- If an issue from d_03 is fixed, mark ✅ and move on.
- If an issue persists, document the specific shortfall and mark ❌.
- Do NOT introduce new findings beyond d_03 scope unless they are CRITICAL for KE execution.
- Your verdict gates Knowledge Extractor execution: READY=go, NEEDS_FIX=iterate, NEEDS_ESCALATION=human review.

---

## Deliverables

| Artifact | Type | Purpose |
|----------|------|---------|
| d_06_expert_reviewer_ipc_revalidation_report.md | Report | Re-validation results + verdict |

**Next step after your output**:
- If READY → Knowledge Extractor execution can begin (p_05 task)
- If NEEDS_FIX → Expert executes p_03 again to create d_07, d_08 (third cycle)
- If NEEDS_ESCALATION → User reviews and decides next action
