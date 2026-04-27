# START HERE: Restore Copilot Context On New Computer

Use this handoff package to continue work without restarting from zero context.

## Files in this package

- chat_transcript.jsonl: full conversation transcript from previous machine
- session_memory.md: session context and decisions summary
- repo_memory.md: repository-specific stable remediation rules

## Minimum setup on new computer

1. Clone repository and checkout working branch.
2. Restore non-git artifacts if needed (sample sources, DB files, out artifacts).
3. Open this repository in VS Code.
4. Start a new Copilot Chat and paste the bootstrap message below.

## Bootstrap message for first Copilot prompt

Copy and paste this text into the first message of a new Copilot Chat:

---
Please continue this project using the following handoff context files:
- out/handoff/session_memory.md
- out/handoff/repo_memory.md
- out/handoff/chat_transcript.jsonl

Working context to load first:
- out/ipc_2/d_07_ipc.adapter.md
- out/ipc_2/d_08_knowledge-extractor-ipc.instructions.md
- out/ipc_2/d_10_ipc_knowledge_extraction_report.md
- out/ipc_2/d_11_expert_reviewer_ke_full_review_report.md
- KNOWLEDGE_EXTRACTOR_ROLE_PROMPT.md
- KNOWLEDGE_EXTRACTOR_WORKFLOW_ALGORITHM.md
- SYSTEM_SYNTHESIZER_ROLE_PROMPT.md
- KE_SYSTEM_SYNTHESIZER_BOUNDARY.md
- EXPERT_REVIEWER_ROLE_PROMPT.md
- EXPERT_REVIEWER_WORKFLOW.md

Goal:
Resume from post-d_11 state. Apply reviewer warnings, update d_10 as needed, re-run KE full review, then proceed to synthesis stage and synthesis review.

Required discipline:
- run_id-scoped DB evidence
- confidence/ambiguity rules
- Layer A/B vs Layer C boundary
- observed vs inferred labeling
---

## Optional: quick integrity checks

- Verify transcript file exists and is non-empty
- Verify d_07/d_08/d_10/d_11 exist under out/ipc_2
- Verify branch and commit match expected working state

## Note

Copilot chat UI session state itself is not portable as a live tab, but this package reproduces practical working context with high fidelity.
