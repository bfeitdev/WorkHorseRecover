# Final V1.0.0 Regression Report

- Installed package version: rdi-recover 1.0.0
- Python version: 3.13.15
- Operating system: Darwin 24.6.0
- Synthetic test result: 22 tests, OK
- Code changes made during this regression: added `final_regression_verify.py` for regression verification only; no recovery or packaging logic changes

| Check | Dataset A | Dataset B |
| --- | --- | --- |
| Installed CLI used | PASS | PASS |
| Ensemble count reproduced | PASS | PASS |
| Chronology reproduced | PASS | PASS |
| Gap accounting reproduced | PASS | PASS |
| Fragment classification reproduced | PASS | N/A |
| Counter reset handling | PASS | PASS |
| Configuration continuity | PASS | PASS |
| Provenance map verified | PASS | PASS |
| Full byte identity verified | PASS | PASS |
| Final structural validation | PASS | PASS |
| Report consistency | PASS | PASS |

## Dataset A Summary

- Verdict: PASS_WITH_UNRECOVERABLE_FRAGMENTS
- Accepted complete ensembles: 6491
- Source valid ensembles: [2801, 3690]
- Chronological order: ['stnr0879_LADCPM.000', 'strn0879_LADCPM_RDI.000']
- Nominal cadence: 1000 ms
- Gaps: 1
- Missing acquisition time: 90.670 s
- Estimated missing ensembles: 91
- Validation issues: 0

## Dataset B Summary

- Verdict: PASS_WITH_GAPS
- Accepted complete ensembles: 847
- Source valid ensembles: [50, 675, 102, 20]
- Chronological order: ['_RDI_001.000', '_RDI_002.000', '_RDI_003.000', 'MLADC001.000']
- Nominal cadence: 1000 ms
- Gaps: 3
- Missing acquisition time: 4033.560 s
- Estimated missing ensembles: 4034
- Validation issues: 0

## Defects Found

- none

READY_FOR_V1.0.0
