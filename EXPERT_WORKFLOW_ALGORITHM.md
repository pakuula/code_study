# Expert Workflow Algorithm

Purpose: universal execution algorithm for Expert across domains.

## Inputs
- Task request.
- DB path.
- run_id.
- Generic guide.
- Optional adapter and prior context reports.

## Step 1: Normalize Task Scope
- Extract explicit deliverables and constraints.
- Identify prohibited outputs.
- Define success criteria.

## Step 2: Bind Baseline Method
- Load generic guide and Expert role rules.
- Confirm global files remain domain-neutral.

## Step 3: Adapter Handling
- If adapter exists: validate freshness and evidence sufficiency.
- If adapter does not exist: generate adapter from DB evidence.
- Keep adapter schema normalized and confidence-labeled.

## Step 4: Evidence Collection
- Query v_type_uses for entity and type evidence.
- Query v_call_in for call-flow and transition evidence.
- Use raw_context for conditional paths and mode markers.
- Enforce run_id scoping in all queries.

## Step 5: Candidate Evaluation
- Confirm candidates with structural signals:
  - func_param and func_return coverage
  - local_var co-usage
  - field-level presence where relevant
  - call-graph adjacency to representative functions
- Score candidates and classify:
  - confirmed
  - weak or ambiguous
  - absent in current index

## Step 6: Confidence and Ambiguity Pass
- Attach confidence level and detector/source basis.
- Expand ambiguity groups into explicit candidate lists.
- Mark MEDIUM and LOW claims as requiring verification.

## Step 7: Artifact Materialization
- Write requested artifacts only.
- Include rationale for selected entities and API prefixes.
- Include unresolved ambiguities and caveats.
- If quality gates fail, mark status PARTIAL and include next queries.

## Step 8: Output Validation
- Check required sections and file paths.
- Ensure constraints were respected.
- Ensure no out-of-scope report generation.

## Step 9: Validate Against Consumer Contract
- Validate handoff artifacts against the expected consumer interface.
- Confirm mandatory fields exist: metadata, entities, API anchors, confidence notes, ambiguity notes, query params.
- Confirm confidence and ambiguity constraints are preserved for downstream use.
- If contract mismatch is found, fix artifacts before final response.

## Reusable Decision Rule For New Seed Concepts
For each new concept requested by user:
1. Search evidence in DB views and raw_context.
2. If confirmed: add to seeds with source and confidence.
3. If weak/ambiguous: add to confidence notes with verification TODO.
4. If absent: mark explicitly as absent in current index.
5. Check likely spelling variants and document ambiguity (example: fact call vs fast call).
