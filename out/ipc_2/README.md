# IPC v2 Workflow — Artifact Navigation Guide

**Directory**: /out/ipc_2  
**Last Updated**: 2026-04-26  
**Status**: Cycle 2 prompts ready; awaiting Expert remediation execution

---

## File Organization Scheme

Files follow naming pattern: `[TYPE]_[SEQ]_[DESCRIPTION].[md|prompt.md]`
- **p_NNN** = Prompt files (inputs for agents)
- **d_NNN** = Deliverable files (outputs from agents)
- Sequence reflects creation/iteration order

---

## Cycle 1: Initial Build → Validation (✅ Completed)

### Input Prompts

| File | Agent | Purpose | Status |
|------|-------|---------|--------|
| **p_01_expert_ipc_adapter_and_ke_task.prompt.md** | Expert | Build IPC adapter v1 from scratch | ✅ Executed |
| **p_02_expert_reviewer_ipc_preflight.prompt.md** | Expert Reviewer | Preflight validation of v1 outputs | ✅ Executed |

### Deliverables

| File | Source | Purpose | Status |
|------|--------|---------|--------|
| **d_01_ipc.adapter.md** | Expert (p_01) | IPC domain bindings (entities, seeds, API) | ⚠️ NEEDS_FIX (per d_03) |
| **d_02_knowledge-extractor-ipc.instructions.md** | Expert (p_01) | Consumer contract for KE execution | ⚠️ Blocked (depends on d_01 fix) |
| **d_03_expert_reviewer_ipc_preflight_report.md** | Reviewer (p_02) | 10 findings: 4 CRITICAL, 2 HIGH, 3 MEDIUM, 1 LOW | ✅ Reference for cycle 2 |

**Cycle 1 Verdict**: **NEEDS_FIX** — d_01 fails contract compliance; blockers documented in d_03

---

## Cycle 2: Remediation → Re-validation (🔄 Ready to Execute)

### Input Prompts

| File | Agent | Purpose | Status | Next Step |
|------|-------|---------|--------|-----------|
| **p_03_expert_ipc_remediation_task.prompt.md** | Expert | Fix d_03 findings → create NEW d_04, d_05 | 📋 Ready | runSubagent(Expert, p_03) |
| **p_04_expert_reviewer_ipc_revalidation.prompt.md** | Expert Reviewer | Re-validate d_04, d_05 → READY or NEEDS_FIX | 📋 Ready | runSubagent(Reviewer, p_04) after d_04/d_05 exist |

### Expected Deliverables

| File | Source | Purpose | Status | Pre-condition |
|------|--------|---------|--------|---------------|
| **d_04_ipc.adapter.md** | Expert (p_03) | Remediated adapter (C1–C4, H2–H3 fixed) | ⏳ Pending | p_03 execution |
| **d_05_knowledge-extractor-ipc.instructions.md** | Expert (p_03) | Updated consumer instruction (binds to d_04) | ⏳ Pending | p_03 execution |
| **d_06_expert_reviewer_ipc_revalidation_report.md** | Reviewer (p_04) | Re-validation verdict + detailed findings | ⏳ Pending | p_04 execution |

**Cycle 2 Target Verdict**: **READY** — All blockers fixed, contract satisfied, gates KE execution

---

## Cycle 3: Knowledge Extraction (⏳ Future, post-d_06 READY)

**Prompts** (to be created):
- **p_05_knowledge_extractor_ipc_task.prompt.md** — KE execution task
- **p_06_expert_reviewer_ipc_full_review.prompt.md** — Full review (different from preflight)

**Deliverables** (to be created):
- **d_07_ipc_knowledge_extraction_report.md** — Feature extraction output
- **d_08_expert_reviewer_ipc_full_review_report.md** — Delivery validation

**Pre-condition**: d_06 verdict = READY

---

## Blocker Fixes Reference (from d_03)

**CRITICAL Blockers** (must fix for d_06 = READY):
1. **C1**: Replace `fastpath_call` (not real entity) or caveat it
2. **C2**: Correct seed counts with DB queries (shared: 16→7, fast: 19→6, local: 27→4)
3. **C3**: Document `receiveIPC` CONFIG_KERNEL_MCS conditional presence
4. **C4**: Verify `seL4_IPCBuffer` evidence (expected ~15, not 5)

**HIGH Blockers** (improves contract compliance for d_06 = READY):
5. **H2**: Document API prefix filtering methodology (exact queries + detector per prefix)
6. **H3**: Add confidence discipline section (detector attribution + ambiguity audit)

**Details**: See d_03_expert_reviewer_ipc_preflight_report.md (10 findings, ~80KB)

---

## Key Constraints for Remediation

**p_03 Execution** (Expert remediation task):
- ✅ Create NEW files d_04, d_05 (do NOT modify d_01, d_02)
- ✅ Fix all C1–C4 blockers with DB-backed evidence
- ✅ Fix H2–H3 scope/contract issues
- ✅ Output status: d_04 metadata `status: READY` only if all fixes verified
- ✅ Maintain traceability: d_01/d_02 stay immutable for audit trail

**p_04 Execution** (Expert Reviewer re-validation):
- ✅ Check all 6 blockers (C1–C4, H2, H3) against d_04/d_05
- ✅ Verify contract compliance (mandatory KE consumer fields)
- ✅ Output verdict: READY | NEEDS_FIX | NEEDS_ESCALATION
- ✅ If READY: gates Knowledge Extractor execution
- ✅ If NEEDS_FIX: identifies additional fixes; cycle 3 with d_07/d_08

---

## Handoff Contract Requirements (KE Consumer)

**Mandatory in d_04**:
- ✅ Metadata: feature_label, db_path, run_id, status
- ✅ Entities: primary + supporting (with detector + confidence)
- ✅ API: prefixes with evidence methodology + detector per prefix
- ✅ Representative functions: file:line + detector + confidence
- ✅ Confidence notes: detector source + confidence rationale per entity
- ✅ Ambiguity notes: ambiguity_group audit results
- ✅ YAML frontmatter (optional but recommended for consistency)

**Mandatory in d_05**:
- ✅ Adapter binding: points to d_04 (not d_01)
- ✅ Output structure: 10 sections with per-item fields (claim, source, detector, confidence, status)
- ✅ Seed validation rule: reflects d_04 corrected seed counts
- ✅ YAML frontmatter: description, applyTo

---

## Execution Roadmap

```
p_01 (build)
  ↓ [Expert executed]
  d_01, d_02
  ↓ [Reviewer validated]
p_02 (preflight)
  ↓
  d_03 (10 findings: NEEDS_FIX verdict)
  ↓
p_03 (remediate C1–C4, H2–H3)
  ↓ [Expert executes NEXT]
  d_04, d_05 (should be status: READY)
  ↓ [Reviewer re-validates NEXT]
p_04 (re-validation)
  ↓
  d_06 (verdict: READY or NEEDS_FIX)
  ↓ [if READY]
  → Knowledge Extractor execution gates open
  → Create p_05, p_06 for KE + full review
  ↓ [if NEEDS_FIX]
  → Iterate: Expert creates d_07, d_08 (cycle 3)
  → Reviewer creates d_09 (cycle 3 preflight)
```

---

## Quick Reference: File Roles

**Prompts** (inputs for agents):
- **p_01**: Expert builds adapter v1
- **p_02**: Reviewer validates v1
- **p_03**: Expert fixes v1 issues → v2 (d_04, d_05)
- **p_04**: Reviewer validates v2
- **p_05**: (future) KE executes extraction
- **p_06**: (future) Reviewer final validation

**Deliverables** (agent outputs):
- **d_01**: IPC adapter v1 (NEEDS_FIX)
- **d_02**: KE instruction v1 (depends on d_01)
- **d_03**: Preflight report v1 (10 findings; audit trail)
- **d_04**: IPC adapter v2 remediated (awaiting creation)
- **d_05**: KE instruction v2 (awaiting creation)
- **d_06**: Re-validation report v2 (awaiting creation)
- **d_07+**: (future) KE output + full review outputs

---

## How to Navigate This Directory

**For cycle 2 execution**:
1. Read **p_03_expert_ipc_remediation_task.prompt.md** (Expert task specification)
2. Execute: `runSubagent(Expert, p_03)`
3. Expert produces: d_04_ipc.adapter.md + d_05_knowledge-extractor-ipc.instructions.md
4. Read **p_04_expert_reviewer_ipc_revalidation.prompt.md** (Reviewer task)
5. Execute: `runSubagent(Reviewer, p_04)`
6. Reviewer produces: d_06_expert_reviewer_ipc_revalidation_report.md

**For understanding blocker fixes**:
- See d_03_expert_reviewer_ipc_preflight_report.md (detailed 10 findings + queries)
- Reference section: "Blocking Fixes Required" lists 6 fixes (C1–C4, H2, H3)

**For contract validation**:
- See d_03, section: "Handoff Contract Compliance Audit"
- Verify d_04/d_05 satisfy same table in d_06 re-validation

---

**Status**: Ready for cycle 2 execution  
**Next Step**: Execute p_03 with Expert, then p_04 with Reviewer
