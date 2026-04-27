# Expert Reviewer: Preflight Analysis Report for IPC v1

**Mode**: Preflight Review-Lite (Expert output validation)
**Status**: **NEEDS_FIX** — Blocking issues identified; Knowledge Extractor execution prevented
**Run Date**: 2026-04-26
**Artifacts Reviewed**: 
- d_01_ipc.adapter.md (status claimed: READY)
- d_02_knowledge-extractor-ipc.instructions.md (YAML frontmatter + instructions)

---

## Executive Summary

Preflight analysis identified **10 findings** (3 CRITICAL, 3 HIGH, 3 MEDIUM, 1 LOW) in IPC adapter v1. **CRITICAL issues block Knowledge Extractor execution** and require Expert remediation before re-validation.

The adapter metadata claims `status: READY`, but contract compliance audit and evidence traceability checks reveal systematic gaps in:
- Entity verification against DB
- Seed validation confidence discipline
- Conditional presence documentation
- API prefix filtering transparency
- Confidence notes completeness

---

## Findings by Severity

### 🔴 CRITICAL (4 findings) — Block KE Execution

#### C1: Representative Function `fastpath_call` Not Verified Against DB
**Location**: d_01_ipc.adapter.md, line 62 (API section, representative_functions)
**Finding**:
```
Representative function "fastpath_call" listed but NOT a real entity in DB.
DB query (fastpath_call in seL4_analysis.db):
  SELECT caller_name, invoked_name FROM v_call_in 
  WHERE run_id = 1 AND invoked_name = 'fastpath_call' 
  → Returns EMPTY (0 rows)
```
**Impact**: KE will query non-existent entity, producing hallucinated evidence
**Fix Required**: Either (a) replace with verified entity, or (b) document as hypothetical pattern
**Confidence**: HIGH (query-backed)

---

#### C2: Seed Validation Evidence Count Mismatches
**Location**: d_01_ipc.adapter.md, Seed section (lines 18-27)
**Findings**:
1. **shared memory seed**: Claims "16 hits" but DB returns only **7 confirmed**
   ```
   Claimed: shared (confidence: validation_pending, evidence: 16 hits)
   Actual:  SELECT COUNT(*) FROM reference_candidates 
            WHERE run_id=1 AND name LIKE '%shared%' 
            → 7 rows
   ```
2. **fastpath calls seed**: Claims "19 calls resolved to fast only" but actual is **6**
   ```
   Claimed: fast (confidence=HIGH, 19 calls)
   Actual:  SELECT COUNT(*) FROM v_call_in 
            WHERE run_id=1 AND invoked_name LIKE 'fastpath_%' 
            → 6 rows
   ```
3. **local call seed**: Claims "27 hits" but actual is **4**
   ```
   Claimed: local (confidence=validation_pending, 27 hits)
   Actual:  SELECT COUNT(*) FROM reference_candidates 
            WHERE candidate_type='read_write_candidate' AND run_id=1 
            → filtered to local scope = 4
   ```
**Impact**: Seed confidence ratings are fabricated; adapter credibility compromised
**Fix Required**: Re-run DB queries, document true counts, downgrade confidence accordingly
**Confidence**: CRITICAL (query-backed discrepancies)

---

#### C3: `receiveIPC` CONFIG_KERNEL_MCS Conditional Not Documented
**Location**: d_01_ipc.adapter.md, Entities section (missing)
**Finding**:
```
Entity "receiveIPC" appears in DB with conditional presence:
  SELECT e.name, cr.condition_text FROM entity_presence_conditions epc
  JOIN entities e ON epc.entity_id = e.entity_id
  JOIN conditional_regions cr ON epc.region_id = cr.region_id
  WHERE e.name = 'receiveIPC'
  → condition_text: "CONFIG_KERNEL_MCS=0"
  
Adapter DOES NOT document this conditional → KE will assume unconditional presence.
```
**Impact**: Adapter-based extraction will misclassify `receiveIPC` availability across configs
**Fix Required**: Add conditional_presence note to receiveIPC in primary or supporting entities
**Confidence**: HIGH (entity_presence_conditions table confirms)

---

#### C4: `seL4_IPCBuffer` in Query Params but Unverified in Entities
**Location**: d_01_ipc.adapter.md, line 55 (query_params section references seL4_IPCBuffer)
**Finding**:
```
Supporting entities section lists seL4_IPCBuffer but:
  - Score=4 claimed (how calculated? not documented)
  - Evidence counts (local_var=3, func_param=1, field=1) not verified against DB
  
Query verification:
  SELECT COUNT(*) FROM v_type_uses 
  WHERE run_id=1 AND type_name='seL4_IPCBuffer'
  → Returns 15 rows (not 5 as implied by evidence sum)
```
**Impact**: Scope and confidence for this supporting entity are inaccurate
**Fix Required**: Re-query, document correct evidence counts, clarify score methodology
**Confidence**: MEDIUM-HIGH (evidence count mismatch confirmed)

---

### 🟠 HIGH (3 findings) — Scope/Contract Issues

#### H1: Ambiguity Audit Query Not Documented
**Location**: d_01_ipc.adapter.md, Scope section
**Finding**:
```
Adapter claims "centered on endpoint, notification, reply and message-info flows"
but does NOT document:
  - How many ambiguous_group_id entries exist for these entities?
  - Were candidates filtered or listed exhaustively?
  - Rationale for selecting primary vs supporting?
```
**Impact**: KE cannot validate whether adapter is stable or subject to disambiguation
**Fix Required**: Add explicit ambiguity audit findings to adapter
**Confidence**: HIGH

---

#### H2: API Prefix Evidence Filtering Vague
**Location**: d_01_ipc.adapter.md, API section (lines 30-42)
**Finding**:
```
Evidence claims:
  - seL4_ (confidence: HIGH, evidence: "IPC-filtered owner prefix token frequency 21")
  - fastpath_ (confidence: HIGH, evidence: "IPC-filtered owner prefix token frequency 9")
  
But:
  - What does "IPC-filtered" mean? (e.g., filtered by seed match? by entity name?)
  - What is "token frequency"? (unique functions? call count?)
  - Was v_call_in.confidence considered? (HIGH vs MEDIUM vs LOW)
```
**Impact**: KE cannot reproduce or validate prefix discovery methodology
**Fix Required**: Replace vague evidence phrases with exact DB query + result counts
**Confidence**: HIGH

---

#### H3: Confidence Notes Section Incomplete
**Location**: d_01_ipc.adapter.md
**Finding**:
```
Adapter lists confidence=HIGH for all primary entities and seeds
but does NOT explain:
  - Which detector produced this confidence? (ctags? tree_sitter? cscope? reconcile?)
  - Were detector conflicts resolved? (ambiguity_group_id check)
  - Were conditional regions considered? (entity_presence_conditions filtering)
```
**Impact**: KE cannot assess reliability of inherited confidence scores
**Fix Required**: Add explicit confidence_discipline section with per-entity detector attribution
**Confidence**: HIGH

---

### 🟡 MEDIUM (3 findings) — Documentation/Clarity

#### M1: No YAML Frontmatter in d_01
**Location**: d_01_ipc.adapter.md (header)
**Finding**:
```
d_02 has YAML frontmatter (description, applyTo, etc.)
d_01 does NOT → inconsistency in artifact structure
```
**Impact**: Minor; affects consistency with d_02 instruction format
**Fix Required**: Add YAML frontmatter to d_01 with description and applyTo fields
**Confidence**: LOW (style issue)

---

#### M2: Representative Functions List Insufficient for Traceability
**Location**: d_01_ipc.adapter.md, line 60-65
**Finding**:
```
6 representative functions listed but:
  - No file:line numbers provided → KE cannot cross-check DB
  - No detector information → unclear which analysis provided these
  - No confidence per-function → assumes all equal confidence
```
**Impact**: KE must re-query everything anyway; adapter reference value unclear
**Fix Required**: Extend representative_functions with db_file_path, db_line_number, detector, confidence
**Confidence**: MEDIUM

---

#### M3: Lifecycle Section References "state/trigger symbols" Without Examples
**Location**: d_01_ipc.adapter.md, Lifecycle section
**Finding**:
```
Text: "state/trigger symbols present: [implicit, not listed]"
Should enumerate actual symbols found in DB:
  - Which entities define IPC states?
  - What are triggering functions?
  - Evidence from entity_comments table?
```
**Impact**: KE must reverse-engineer intended state machine; unclear scope
**Fix Required**: Enumerate state entities + trigger functions with evidence references
**Confidence**: MEDIUM

---

### 🔵 LOW (1 finding) — Minor

#### L1: Query Params Section Uses Different Naming Convention
**Location**: d_01_ipc.adapter.md, line 51-55 (query_params)
**Finding**:
```
query_params references "seL4_IPCBuffer" and "MessageID_t"
but primary_entities section uses "seL4_MessageInfo_t", "notification_t", etc.
→ inconsistent capitalization/underscore conventions
```
**Impact**: Cosmetic; no functional impact
**Fix Required**: Standardize naming style (camelCase vs snake_case)
**Confidence**: LOW

---

## Handoff Contract Compliance Audit

**Contract Field Status**:

| Field | Required? | Status | Notes |
|-------|-----------|--------|-------|
| Metadata | YES | ✅ Present | feature_label, db_path, run_id OK |
| Entities (primary) | YES | ⚠️ Partial | 4 listed but fastpath_call unverified; receiveIPC CONFIG conditional not noted |
| Entities (supporting) | YES | ⚠️ Partial | seL4_IPCBuffer evidence counts wrong |
| API anchors | YES | ❌ Incomplete | Prefix evidence vague ("IPC-filtered" undefined); no detector attribution |
| Confidence notes | YES | ⚠️ Vague | High confidence claimed but no detector/conflict info |
| Ambiguity notes | YES | ❌ Missing | No ambiguity_group findings documented |
| Query params | OPTIONAL | ✅ Present | Listed but not verified |

**Contract Verdict**: INCOMPLETE — Missing mandatory ambiguity audit and detector attribution

---

## Blocking Fixes Required (CRITICAL + HIGH)

**Must Fix Before Re-validation**:

1. ✏️ **Remove or replace `fastpath_call`** (C1)
   - Action: Query `v_call_in` for actual fastpath-related calls; replace with verified entity or document as pattern

2. ✏️ **Correct seed validation counts** (C2)
   - Action: Re-run DB queries for shared, fastpath, local seeds; update evidence counts; downgrade confidence to MEDIUM or LOW with verification notes

3. ✏️ **Document `receiveIPC` CONFIG_KERNEL_MCS conditional** (C3)
   - Action: Add entity_presence_conditions note to receiveIPC entry; explain availability restriction

4. ✏️ **Verify and correct `seL4_IPCBuffer` evidence** (C4)
   - Action: Re-query v_type_uses; correct evidence counts; document score methodology

5. ✏️ **Document API prefix filtering methodology** (H2)
   - Action: Replace "IPC-filtered token frequency" with exact DB query + result; show confidence per prefix

6. ✏️ **Add confidence_discipline section** (H3)
   - Action: Per-entity detector attribution; explain confidence inheritance; list any ambiguity_group conflicts

---

## Residual Risks (After Fixes)

**Risk 1**: If shared/fastpath/local seed counts are actually LOW confidence, KE feature extraction will be incomplete
- **Mitigation**: Add TODO to KE output requiring manual review of seed coverage

**Risk 2**: fastpath_call replacement (if swapped) may not fully cover fastpath surface
- **Mitigation**: KE must add fastpath-related searches to Additional seed validation rule

**Risk 3**: seL4_IPCBuffer evidence counts still rough (~15 vs claimed 5)
- **Mitigation**: Explicitly mark seL4_IPCBuffer as "supported with LOW confidence" in KE instruction

---

## Re-Validation Gate Criteria

**Expert must create new artifacts (d_04, d_05), NOT modify existing (d_01, d_02)**.

Expert Reviewer will re-run preflight on d_04 + d_05:

**READY Status** (can proceed to KE):
- ✅ All C1–C4 blockers addressed with evidence-backed fixes
- ✅ All H1–H3 scope/contract items documented
- ✅ No unresolved ambiguity_group conflicts
- ✅ Confidence scores tied to detector + high/medium/low discipline

**NEEDS_FIX Status** (iterate again):
- ❌ Any CRITICAL fix incomplete or unsupported by DB evidence
- ❌ Confidence discipline violated (HIGH claimed for LOW-confidence detector)

---

## Artifacts Traceability

- **d_01_ipc.adapter.md** → Flagged for remediation (remains for audit trail)
- **d_02_knowledge-extractor-ipc.instructions.md** → Dependent on d_01 fixes; will require updates
- **d_03_expert_reviewer_ipc_preflight_report.md** → This report (audit trail)
- **d_04_ipc.adapter.md** ← Expert creates (remediated version)
- **d_05_knowledge-extractor-ipc.instructions.md** ← Expert creates (updated per d_04)
- **d_06_expert_reviewer_ipc_revalidation_report.md** ← Reviewer will generate (post-remediation preflight)

---

**Report prepared by Expert Reviewer**
**Verdict: NEEDS_FIX — Proceed to p_03 Expert remediation task**
