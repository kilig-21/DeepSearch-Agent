# H1 final-run manifest

| group | run | table | adapter env | command / notes |
|---|---|---|---|---|
| pure_web A | `run_20260908_205824.json` | `table_20260908_205824.md` | unset | locked eight-qid reflect command; completed 8/8 |
| adapter B | `run_20260909_000658.json` | `table_20260909_000658.md` | `python_zh_docs` | locked eight-qid reflect command; 7 completed and `noanswer_pep` execution_error after per-task budget exhaustion |

Code includes adapter fixes `b0093d0` and `e62e4a1`. No source, threshold, qid list, strategy, or preregistration definition was changed. The smoke `run_20260908_204050.json` validated the channel only and is excluded from comparison. No PLAN.md or README.md was changed.
