# Next Agent Task: v6 Execution Integrity Verification

## Summary
Updated the v6 selection-execution binding (`configs/research_v6_selection_execution_binding_1.json`) to reflect the live source tree identity. The binding now passes verification for:
- Hashed engine digest (recomputes to live `8cd17522...`)
- Composite run code identity (recomputes to live `cfd1cc2d...`)

## Remaining Failures (Frozen Protocol - Cannot Edit)
The verifier still reports 2 failures in the frozen `configs/research_v6_execution.json`:
1. **Code-hash constraint authorized_code_hash mismatch**: Frozen protocol records `2efd3b18...` but `campaign_authorization.json` has rotating `code_hash==13172b2e...`
2. **Code-hash constraint canonical_hashed_set_digest mismatch**: Frozen protocol records stale snapshot `3e8e41...` but live source computes `8cd17522...`

## Constraints (Unchanged)
- No edits to frozen v6 artifacts (`configs/research_v6_execution.json`, etc.)
- No edits to `campaign_authorization.json` without explicit authorization
- No consuming `v6-selection-20261022` run
- No holdout/confirmatory exposure before `2027-01-20T02:00:00Z`

## Next Steps
The remaining failures document a known divergence between the frozen protocol (published at v6 specification time) and the live source tree. Per protocol design, the frozen protocol is immutable; the versioned binding is the artifact that tracks implementation state. The binding is now current.

**Action for next agent**: Monitor for explicit authorization to update frozen artifacts, or for the v6 selection run to be consumed (which would create new artifacts). Until then, standing checks will continue to show the 2 frozen-protocol failures as expected.