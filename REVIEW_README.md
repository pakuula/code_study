# Review Workflow Quick Guide

This document explains which review prompt template to use and in what order.

## Files
- `EXPERT_REVIEWER_ROLE_PROMPT.md` - role and responsibility model for Expert Reviewer.
- `EXPERT_REVIEWER_WORKFLOW.md` - validation workflow and verdict policy.
- `REVIEW_PROMPT_TEMPLATE.md` - generic template for custom review tasks.
- `REVIEW_PROMPT_PREFLIGHT_EXPERT.md` - ready-to-use preflight review for Expert outputs.
- `REVIEW_PROMPT_FULL_KE.md` - ready-to-use full review for Knowledge Extractor outputs.

## When To Use Which Template
1. Use `REVIEW_PROMPT_PREFLIGHT_EXPERT.md` before running Knowledge Extractor.
2. Use `REVIEW_PROMPT_FULL_KE.md` after Knowledge Extractor produces final output.
3. Use `REVIEW_PROMPT_TEMPLATE.md` for new domains, custom pipelines, or non-standard artifacts.

## Recommended Sequence
1. Preflight gate:
   - Run reviewer with `REVIEW_PROMPT_PREFLIGHT_EXPERT.md`.
   - Expected result: `READY`.
   - If `NEEDS_FIX`, apply blocking fixes and re-run preflight.
2. Producer run:
   - Run Knowledge Extractor only after preflight is `READY`.
3. Full gate:
   - Run reviewer with `REVIEW_PROMPT_FULL_KE.md`.
   - Expected result: `PASS` or `PASS_WITH_WARNINGS`.
   - If `FAIL`, fix and re-run full review.

## Status And Verdict Meanings
- `READY`: handoff artifacts are valid for downstream execution.
- `NEEDS_FIX`: blocking issues in producer artifacts.
- `PASS`: all mandatory checks satisfied.
- `PASS_WITH_WARNINGS`: non-critical issues remain.
- `FAIL`: critical contract or evidence violations.

## Minimal Run Instructions
1. Pick the appropriate prompt file.
2. Fill placeholders (artifact paths, db path, run_id, target label).
3. Run Expert Reviewer with that prompt.
4. Apply required fixes and repeat until gate criteria are met.

## Notes
- Keep domain specifics in adapter and domain instruction files.
- Keep generic methodology files domain-neutral.
- Always preserve confidence and ambiguity discipline in both preflight and full review.
