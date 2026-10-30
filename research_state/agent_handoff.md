# Durable agent handoff (top block — read first)

**Campaign state:** steady v6 freeze (authoritative). No open implementation tracks; campaign progression blocked pending CONFIRMATORY_WINDOW.

**Verification (authoritative; re-run this session, all exit 0 with ok:true):**
- scripts/verify_research_v6_spec.py: ok:true (declared == recomputed spec hash 4a07911a1e0a79e0489e0ff638526ffeef2f2d217696e80308c77b440dbeac9c)
- scripts/verify_research_v6_manifests.py: ok:true (data_manifest_v6 a9c6c492d92dd323685722a70f586a155631d24b1c4e8fa34113ffd2d5dc1465, universe_manifest_v6 baac2b942ea76749cffc7a71940fe03496e2416a358940c8e7972036b7295072; 497664/497664 records)
- scripts/verify_research_v6_candidate_freeze.py: ok:true (manifest 3b482a4f25c575cbe1e2bd9a8d787a76caf34be0e76de03b0e14b0daa70fbec4; 20 frozen band, 7 validated)
- scripts/verify_v6_execution.py: ok:true (manifest 928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026; v6-selection-20261022, selection auth f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; inherited blocks digest 0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433)
- scripts/verify_v6_confirmatory_protocol.py: ok:true (manifest 71f7322f66147cb63f0e05da6f8ff816331fcda8c0829d07a6a3a2b2f5928ad4)
- scripts/verify_v6_confirmatory_runbook_1.py: ok:true (manifest dd95b653b62e55059bec908c07530870418612b6fd841d74a5ab44803dae273b)
- scripts/verify_v6_universe_expansion_log.py: ok:true (4 entries v3-v6, head entry hash 596af09668d0ffcc5d323beb6d71d32fdcb62fd47d120652e82643d8e60512b1)
- ./check_progress.sh: ok:true; records 497664/497664; completed cohorts [0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d, be4223dcef25aaa0043a466fcd9044b4e6a7387eff7efd487561b9c1f873c1ae, v2-selection-20261019, v3-selection-20261020, v4-selection-20261021, v5-selection-20261021]; next_cohort_index=6

**Git:** HEAD 73c2cf08d03aeede80ab6240ea12248b215545ad matches origin/main 73c2cf08d03aeede80ab6240ea12248b215545ad (clean, 0 ahead 0 behind). Verified this session 2026-10-30T12:47:09Z: all seven v6 verifiers exit 0 with ok:true; ./check_progress.sh ok:true (497664/497664 records, next_cohort_index=6). No uncommitted changes. HEAD ed1beb711cbba46d0ec6453ede904536fc495542 matches origin/main ed1beb711cbba46d0ec6453ede904536fc495542, tree clean, 0 ahead 0 behind.

**Authorization:** configs/research_v6_selection_authorization_1.json present (v6-selection-20261022). configs/research_v6_execution_amendment_1.json is effective execution authorization source. All authorization flags in configs/research_v6*.json are false (no evaluation/run authorized). Canonical hashed set digest 3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff; inherited blocks digest 0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433.

**Blocker:** CONFIRMATORY_WINDOW blocks next_cohort_index=6 until 2027-01-20T02:00:00Z. Evaluation may not start before 2027-01-20T02:00:00Z. No implementation authorized without new selection run or new version design.

**Reconciliation:** no reconciliation required (stale research_state/checkpoint.json v1-era noted as legacy; checkpoint_v6.json does not exist).

**Precise next action:** On session resume, re-run the seven v6 verifiers and ./check_progress.sh; acceptance criteria all seven exit 0 with ok:true, git tree clean, 497664/497664 records, next_cohort_index=6 unchanged, HEAD matches origin/main. Only after CONFIRMATORY_WINDOW ends (2027-01-20T02:00:00Z) and with explicit authorization may a new selection run or new version design be undertaken. Prior task (verify state) completed this session (2026-10-30T12:47:09Z).

**Initial task message for next agent:** "Read research_state/agent_handoff.md (top block). Campaign is in steady v6 freeze: verified 2026-10-30T12:45:36Z — all seven v6 verifiers pass (scripts/verify_research_v6_spec.py, scripts/verify_research_v6_manifests.py, scripts/verify_research_v6_candidate_freeze.py, scripts/verify_v6_execution.py, scripts/verify_v6_confirmatory_protocol.py, scripts/verify_v6_confirmatory_runbook_1.py, scripts/verify_v6_universe_expansion_log.py) and ./check_progress.sh all exit 0 with ok:true; live code/hash clean (HEAD 73c2cf08d03aeede80ab6240ea12248b215545ad matches origin/main 73c2cf08d03aeede80ab6240ea12248b215545ad, tree clean, 0 ahead 0 behind). 497664/497664 records complete; next_cohort_index=6 blocked on CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z (evaluation may not start before 2027-01-20T02:00:00Z; authorization flags in configs/research_v6*.json all false — no evaluation or run authorized). Do not implement changes unless explicitly authorized for a new selection run or new version design. Re-run the seven v6 verifiers and ./check_progress.sh on resume to confirm acceptance criteria. Note research_state/checkpoint.json is a stale legacy artifact (v1-era, not v6) and checkpoint_v6.json does not exist."
