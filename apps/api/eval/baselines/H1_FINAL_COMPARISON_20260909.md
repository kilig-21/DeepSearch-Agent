# H1 final A/B comparison and preregistered mechanical ruling

Inputs: A pure Web `run_20260908_205824.json`; B adapter `run_20260909_000658.json`. Smoke is excluded. Final primary metrics use pass2 quote-only annotations in `H1_FINAL_ANNOTATIONS_20260909.json`.

| qid | A strict | B strict | A coverage | B coverage | A evidence/B evidence | A tokens/B tokens | A credits/B credits | A status/B status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| fact_freethread | 100.0% | 100.0% | 66.7% | 66.7% | 3 / 10 | 6,657 / 33,243 | 1 / 0 | completed / completed |
| noanswer_pep | 50.0% | N/A | 100.0% | 0.0% | 14 / 10 | 34,182 / 47,868 | 2 / 0 | completed / execution_error |
| fact_gil | N/A | 87.5% | 0.0% | 83.3% | 0 / 12 | 190 / 47,506 | 1 / 0 | completed / completed |
| fact_venv | N/A | 75.0% | 0.0% | 50.0% | 0 / 10 | 169 / 44,249 | 1 / 0 | completed / completed |
| compare_logging_print | 90.0% | N/A | 100.0% | 0.0% | 6 / 4 | 18,741 / 26,976 | 1 / 0 | completed / completed |
| timely_maint | 62.5% | 75.0% | 100.0% | 33.3% | 9 / 12 | 32,144 / 40,293 | 3 / 0 | completed / completed |
| timely_status | 100.0% | N/A | 100.0% | 0.0% | 6 / 5 | 8,592 / 27,224 | 1 / 0 | completed / completed |
| noanswer_ml | 62.5% | 50.0% | 75.0% | 75.0% | 11 / 11 | 11,092 / 27,263 | 1 / 0 | completed / completed |

| group metric | pure Web | adapter | adapter − pure Web |
|---|---:|---:|---:|
| Strict quote-only assertion support | 17.5/22 = 79.55% | 16/21 = 76.19% | -3.36pp |
| Answer coverage (all 22 required points) | 15/22 = 68.18% | 8.5/22 = 38.64% | -29.55pp |
| Evidence hits | 49 | 74 | +25 |
| Failed tasks | 0/8 = 0.0% | 1/8 = 12.5% | +12.5pp |
| Total / average LLM tokens | 111,767 / 13,971 | 294,622 / 36,828 | +163.6% average |
| Total / average search credits | 11 / 1.375 | 0 / 0 | -100% average |
| Total duration | 1,041.6s | 1,692.0s | +650.4s |

## B adapter event verification

All eight B qids have at least one `search` event with `payload.adapter=python_zh_docs`; counts are 1, 3, 2, 3, 2, 3, 2, 1 respectively. No qid has a `source_adapter` event with `fallback=pure_web`.

`noanswer_pep` executed three adapter searches, then reader warnings recorded insufficient remaining output budget. It consumed 47,868 LLM tokens, exceeded the fixed 50,000-token single-task ceiling when writer allocation was accounted for, produced no report, and ended `execution_error`. This is not described as a network failure.

## Mechanical ruling (§4)

Priority 1, contraction: answer coverage falls 29.55pp (at least 5pp), so the preregistered **contraction-direction** threshold is triggered. Improvement is not considered after that. Independently, B mean LLM tokens are 263.6% of A (well above the 120% condition); search credits are lower but do not cure token-cost failure.

This is a **directional / qualitative observation, not statistical proof** (N=8). The observed pattern is that the adapter increased evidence hits while materially increasing LLM cost and created a real fixed-budget task-failure risk.
