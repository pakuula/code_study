# Feature Extraction Guide

Purpose: produce a high-level, evidence-backed feature report from source index data, without relying on comments as the primary signal.

This guide is domain-neutral. For domain specifics, attach a separate adapter profile.

---

## Inputs

Required:
- SQLite DB path
- run_id
- Feature label (human-readable)
- Domain adapter (keywords, core entities, state/event vocabulary)

Optional:
- Existing analysis report used as context

---

## Phase 0: Adapter Binding

Before data extraction, bind a domain adapter. The adapter must define:
- primary_entities: canonical entities for this feature
- supporting_entities: adjacent entities and aliases
- api_prefixes: function naming anchors
- state_symbols: optional, for lifecycle/state-machine reports
- mode_markers: optional compile-time/runtime variants

If no adapter exists, build one first (see Expert method in `EXPERT_ADAPTER_METHOD.md`).

---

## Phase 1: Core Entity Discovery

Goal: identify entities that form the feature nucleus.

SQL template:
```sql
SELECT DISTINCT type_name, use_context, COUNT(*) AS usage_count
FROM v_type_uses
WHERE run_id = :run_id
   AND type_name IN (:primary_entities)
GROUP BY type_name, use_context
ORDER BY usage_count DESC;
```

Output:
- ranked list of primary entities
- mapping where each entity appears: field, func_param, func_return, local_var

---

## Phase 2: Co-Usage Graph

Goal: discover which entities are used together in implementation contexts.

SQL template:
```sql
SELECT t1.type_name AS left_type,
          t2.type_name AS right_type,
          COUNT(*) AS pair_count
FROM v_type_uses t1
JOIN v_type_uses t2
   ON t1.run_id = t2.run_id
 AND t1.enclosing_function = t2.enclosing_function
WHERE t1.run_id = :run_id
   AND t1.use_context = 'local_var'
   AND t2.use_context = 'local_var'
   AND t1.type_name < t2.type_name
   AND t1.type_name IN (:entity_pool)
   AND t2.type_name IN (:entity_pool)
GROUP BY t1.type_name, t2.type_name
ORDER BY pair_count DESC;
```

Output:
- dependency graph (strong/weak relations by pair_count)

---

## Phase 3: API Surface

Goal: enumerate callable surface associated with the feature.

SQL templates:
```sql
-- Parameters
SELECT owner_name AS api_function,
          GROUP_CONCAT(DISTINCT CASE WHEN by_pointer=1
                THEN type_name || '*'
                ELSE type_name END) AS param_types
FROM v_type_uses
WHERE run_id = :run_id
   AND use_context = 'func_param'
   AND type_name IN (:entity_pool)
   AND (
         owner_name LIKE :prefix_1 OR owner_name LIKE :prefix_2
   )
GROUP BY owner_name
ORDER BY owner_name;

-- Return types
SELECT DISTINCT owner_name AS api_function,
          type_name AS return_type,
          by_pointer
FROM v_type_uses
WHERE run_id = :run_id
   AND use_context = 'func_return'
   AND (
         owner_name LIKE :prefix_1 OR owner_name LIKE :prefix_2
   )
ORDER BY owner_name;
```

Output:
- API table: function, input types, output type, confidence markers

---

## Phase 4: Representative Workflows

Goal: find concrete functions that exercise core entities together.

SQL template:
```sql
SELECT enclosing_function,
          COUNT(DISTINCT type_name) AS covered_entities
FROM v_type_uses
WHERE run_id = :run_id
   AND use_context = 'local_var'
   AND type_name IN (:primary_entities)
GROUP BY enclosing_function
HAVING covered_entities >= :min_coverage
ORDER BY covered_entities DESC, enclosing_function;
```

Output:
- candidate functions for workflow explanation

---

## Phase 5: Source Evidence Extraction

Goal: extract contextual snippets for selected functions.

SQL template:
```sql
SELECT file_path,
          line_number,
          enclosing_function,
          owner_name,
          type_name,
          use_context,
          raw_context,
          detector,
          confidence
FROM v_type_uses
WHERE run_id = :run_id
   AND enclosing_function = :function_name
ORDER BY line_number;
```

Output:
- ordered evidence rows for sequence reconstruction

---

## Phase 6: Sequence and Variants

Goal: infer operation order, mandatory steps, and alternatives.

Minimum checks:
- ordering: operation A usually before B?
- mandatory steps: absent or present in all representative workflows?
- alternatives: mutually exclusive paths?
- conditional paths: compile-time or mode-specific branches?

Helpful SQL templates:
```sql
SELECT file_path, line_number, caller_name, invoked_name, detector, confidence
FROM v_call_in
WHERE run_id = :run_id
   AND caller_name = :function_name
ORDER BY line_number;

SELECT file_path, line_number, raw_context, detector, confidence
FROM v_type_uses
WHERE run_id = :run_id
   AND enclosing_function = :function_name
   AND raw_context LIKE :mode_marker;
```

Output:
- normalized workflow steps
- variants table (mode/arch/config)

---

## Phase 7: Synthesis

Produce a structured report:
- Feature scope
- Core entities
- Entity dependency graph
- API surface
- Representative workflows
- Constraints and invariants
- Variants and boundary conditions
- Confidence and ambiguity notes

For lifecycle-style topics, add:
- states list
- transition table: source state, trigger, target state, evidence

---

## Reporting Rules

- Always include detector and confidence for factual claims.
- If ambiguity_group_id is present, list all candidates.
- Separate observed facts from inferred behavior.
- For MEDIUM/LOW claims, mark as index-derived and requiring verification.

---

## Agent Checklist

- [ ] Adapter bound or generated
- [ ] Core entities identified
- [ ] Co-usage graph built
- [ ] API surface cataloged
- [ ] Representative workflows selected
- [ ] Source evidence extracted
- [ ] Variants and conditionals analyzed
- [ ] Final report synthesized with confidence labels

---

## Limits

What index data usually cannot provide directly:
- design intent
- full runtime semantics
- performance behavior
- complete error propagation logic

Recommended mitigation:
- increase evidence coverage (more representative functions)
- cross-check with additional detectors
- add explicit TODO items for manual validation

---

## Итоговый алгоритм агента (псевдокод)

```
FUNCTION extract_feature(feature_name, db_path):
    1. root_types ← find_core_types(feature_name)
    2. related_types ← find_type_graph(root_types)
    3. api_functions ← find_api_with_types(root_types ∪ related_types)
    4. example_functions ← find_functions_using_all_types(root_types)
    5. FOR each example_function:
        a. code_samples ← get_raw_context(example_function)
        b. sequence ← extract_call_order(code_samples)
        c. constraints ← infer_constraints(sequence)
    6. alternatives ← find_alternative_paths(api_functions)
    7. RETURN synthesize_description(
            types=related_types,
            api=api_functions,
            workflow=sequence,
            examples=code_samples,
            constraints=constraints,
            alternatives=alternatives
        )
```
