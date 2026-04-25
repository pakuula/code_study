# Expert Adapter Method

Purpose: define how the agent named Expert builds a domain adapter from index data and reusable patterns before running feature extraction.

This method keeps the base guide generic and moves domain assumptions into a generated adapter profile.

---

## 1. Contract

Expert must output one adapter document per feature domain.

Suggested path:
- adapters/<feature_slug>.adapter.md

Required sections in adapter:
- feature_label
- scope
- seed_terms
- primary_entities
- supporting_entities
- api_prefixes
- state_symbols
- trigger_symbols
- mode_markers
- exclusion_terms
- confidence_notes
- ready_to_use_query_params

---

## 2. Inputs for Expert

Mandatory:
- DB path
- run_id
- feature label

Optional:
- prior report context
- glossary from user
- known API prefixes

If prior report exists, use it only as hints. Re-validate entities against DB views.

---

## 3. Build Pipeline

### Step A: Seed Term Harvest

Sources for seeds:
- feature label tokens
- user-provided terms
- top nouns from prior report headings and function tables

Normalize terms:
- lower-case
- remove punctuation
- keep short aliases and common prefixes

Output of Step A:
- seed_terms list with provenance

### Step B: Candidate Expansion from DB

Expand seed terms using DB evidence.

SQL templates:
```sql
-- Candidate types by partial term match
SELECT DISTINCT type_name, COUNT(*) AS cnt
FROM v_type_uses
WHERE run_id = :run_id
  AND (
      LOWER(type_name) LIKE :term_1 OR LOWER(type_name) LIKE :term_2
  )
GROUP BY type_name
ORDER BY cnt DESC;

-- Candidate APIs by owner/function name match
SELECT owner_name, use_context, COUNT(*) AS cnt
FROM v_type_uses
WHERE run_id = :run_id
  AND (
      LOWER(owner_name) LIKE :term_1 OR LOWER(owner_name) LIKE :term_2
  )
GROUP BY owner_name, use_context
ORDER BY cnt DESC;
```

Output of Step B:
- entity candidates
- API candidates

### Step C: Relationship Scoring

Score candidates by structural evidence.

Suggested score:
- +3 appears in func_param or func_return
- +2 appears in local_var in representative functions
- +2 appears in field context
- +2 connected to other top candidates via co-usage
- +1 appears in call graph around core functions

Keep top-N as primary_entities, next tier as supporting_entities.

### Step D: API Prefix Discovery

Infer prefix groups from candidate APIs.

Heuristic:
- split function names by underscore/case boundaries
- keep repeated leading tokens with support >= threshold

Output:
- api_prefixes list

### Step E: State and Trigger Discovery (for lifecycle adapters)

Detect state symbols:
- names matching state/status/mode enums
- setter functions and transition-like APIs

Detect trigger symbols:
- verbs like set, block, wake, resume, suspend, fault, delete, revoke

Promote to adapter only if evidence appears in at least two contexts:
- type usage + call site, or
- multiple representative functions

### Step F: Mode/Variant Discovery

Detect markers for conditional paths:
- config and mode macros in raw_context
- architecture tags and platform prefixes

Store as mode_markers for later filtering.

### Step G: Adapter Materialization

Write adapter file in normalized schema with:
- explicit confidence for each section
- unresolved ambiguities and TODO checks
- query parameter block usable by FEATURE_EXTRACTION_GUIDE.md

---

## 4. Quality Gates

Expert can mark adapter READY only if:
- at least one primary entity
- at least three supporting entities or explicit reason why not
- at least one API prefix or explicit fallback pattern
- representative functions found
- confidence notes present

If gates fail:
- return PARTIAL adapter
- include missing evidence list and exact next queries

---

## 5. Adapter Template

Use this template:

```markdown
# Adapter: <feature_label>

## Metadata
- feature_label: <text>
- run_id: <id>
- status: READY | PARTIAL

## Seeds
- seed_terms:
  - <term> (source: label|user|report)

## Entities
- primary_entities:
  - <entity> (score: <n>, confidence: HIGH|MEDIUM|LOW)
- supporting_entities:
  - <entity> (score: <n>, confidence: HIGH|MEDIUM|LOW)

## API
- api_prefixes:
  - <prefix>
- representative_functions:
  - <function>

## Lifecycle (optional)
- state_symbols:
  - <state>
- trigger_symbols:
  - <trigger>

## Variants
- mode_markers:
  - <marker>

## Exclusions
- exclusion_terms:
  - <term>

## Confidence Notes
- <note with detector/confidence and ambiguity if any>

## Ready-to-Use Query Params
- entity_pool: [..]
- primary_entities: [..]
- prefixes: [..]
- mode_markers: [..]
```

---

## 6. Runtime Behavior in Agent Expert

Expert execution order:
1. Build or refresh adapter.
2. Validate adapter quality gates.
3. Run generic feature extraction with adapter params.
4. Emit report plus adapter snapshot for reproducibility.

Key rule:
- never hardcode project-specific terms into the generic guide.
- store domain specifics only in adapter files.
