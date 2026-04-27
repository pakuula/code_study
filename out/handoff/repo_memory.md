# Repo Memory Export

Exported from:
- /memories/repo/ipc_v2_remediation_rules.md

Date: 2026-04-27

---

## ipc_v2_remediation_rules.md

IPC v2 remediation cycle 3 facts (run_id=1, out/seL4_analysis.db):
- local seed broad query must be used: name LIKE '%local%' -> 22 (12 call_candidate/call, 10 read_write_candidate/read)
- receiveIPC conditional must be reported from entity-linked query as directive=ifdef, condition=CONFIG_KERNEL_MCS (not CONFIG_KERNEL_MCS=0)
- fastpath_call is present in v_call_in (3) but absent in entities (0): call-site evidence only, MEDIUM max
- confidence discipline: cscope evidence MEDIUM max; entity-definition evidence (ctags/tree_sitter) can be HIGH when present
