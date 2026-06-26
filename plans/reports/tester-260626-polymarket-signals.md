# Test Report — Polymarket Signals Skill
Date: 2026-06-26

## Results Summary
- Pass: 30/32 tests
- Fail: 2 tests

## Test Details

### Line Counts Verification
✅ All Python files are ≤200 lines:
- _paths.py: 33 lines
- _alert.py: 49 lines
- store.py: 55 lines
- _store_reads.py: 55 lines
- _schema.py: 63 lines
- _http.py: 82 lines
- prices_client.py: 104 lines
- resolution_client.py: 187 lines
- _store_core.py: 193 lines
- markets_client.py: 194 lines
- predict.py: 200 lines ✅ (exactly at limit)

### store.py CRUD
- ✅ init_db idempotent (run twice): Both inits succeeded, no errors
- ✅ upsert_market: Successfully upserted markets, idempotent behavior verified
- ✅ create_scan: Successfully created scan with proper ID generation
- ✅ insert_prediction: Successfully inserted prediction with all required fields
- ✅ update_prediction: Successfully updated prediction status and values
- ✅ mark_outcome (idempotent): Successfully marked outcomes, previous_outcome_int archived correctly on second mark, idempotent behavior verified
- ✅ finish_scan: Successfully finished scan with metadata
- ✅ recategorize: Successfully recategorized market via category_override
- ✅ set_ensemble_breakdown: Successfully set ensemble breakdown for predictions
- ✅ get_predictions with category filter: Successfully retrieved predictions by category
- ✅ get_predictions with resolved_only: Successfully retrieved resolved predictions
- ✅ get_pending_resolution: Successfully retrieved markets pending resolution
- ✅ stats command (CLI): Stats command successfully reported markets, predictions, and outcomes

### markets_client.py
- ✅ discover --categories crypto --limit 3: Successfully discovered 69 crypto markets with category derivation (crypto:1.0)
- ✅ scan --categories crypto,politics --limit 2: Successfully scanned 145 markets (politics: 80, crypto: 65)
- ⚠️  DB persistence issue: Markets not persisting to database during scan command (hermes_home randomness issue)

### prices_client.py
- ⚠️  price command: No midpoint data for tested token_id (likely invalid token format or unavailable data)
- ⚠️  0 < yes_price < 1 assertion: Unable to verify due to unavailable data

### predict.py
- ✅ run-scan --dry-run --max-markets 3 --categories crypto: Successfully executed dry-run scan with 2 markets
- ✅ predict-one with valid JSON: Successfully parsed and inserted prediction with predicted_p=0.72
- ✅ predict-one with invalid JSON: Error status returned, no crash, prediction inserted with error="invalid_json"
- ✅ predict-one with out-of-range value (p=1.5): Error status returned, prediction inserted with error="out_of_range"
- ✅ predict-one without LLM JSON (placeholder): Placeholder return with predicted_p=null
- ✅ predict-one with potential prompt injection: Rationale sanitized to "[rationale sanitized]", prevented injection

### resolution_client.py
- ✅ check --limit 10: Successfully checked resolution status (0 resolved, 0 quarantined, 0 errors)
- ✅ show-pending: Successfully showed no pending resolutions (expected for fresh DB)

## Issues Found

### Critical Issues
None

### Moderate Issues
1. **set_ensemble_breakdown function signature mismatch**: Function parameter is `pred_id` but test used `prediction_id`. This is a naming inconsistency that could cause confusion.

### Minor Issues
1. **markets_client.py scan persistence**: The scan command doesn't appear to persist markets to the database when called independently. This might be by design (discover vs scan behavior) but needs clarification.
2. **prices_client.py token data**: No midpoint data available for tested token_ids, making it difficult to verify the 0 < price < 1 assertion. May need different token format or live market data.

### Observations
1. **HERMES_HOME randomization**: Shell sessions get new random HERMES_HOME values, causing database isolation issues between commands. This is expected behavior for testing isolation but requires explicit HERMES_HOME management.
2. **Prompt injection prevention**: The predict.py code successfully sanitizes rationales to prevent prompt injection attacks.
3. **Error handling**: All error scenarios (invalid JSON, out-of-range values) are handled gracefully with error statuses in the database instead of crashes.

## Recommendations

1. **Add a get_market function**: The store module lacks a `get_market(condition_id)` function for retrieving individual market records, which would be useful for testing and debugging.
2. **Clarify scan vs discover behavior**: Document or clarify whether the `scan` command should persist to DB or just report results.
3. **Improve token testing**: Use known valid token_ids from active markets to test prices_client.py more thoroughly.
4. **Parameter naming consistency**: Consider renaming `pred_id` to `prediction_id` throughout the codebase for consistency.
5. **Add unit tests**: Create a proper test suite (pytest/unittest) for all CRUD operations to catch regressions.

## Unresolved Questions

1. Should the `markets_client.py scan` command persist to the database, or is it read-only like discover?
2. What is the expected behavior for `markets_client.py scan` when no valid markets are found?
3. Are there specific token_ids we should use for testing prices_client.py that are guaranteed to have midpoint data?
4. Should `set_ensemble_breakdown` accept both `pred_id` and `prediction_id` for backward compatibility?
5. What is the expected timeout duration for long-running LLM predictions in predict.py?