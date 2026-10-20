| task_set | task | status | failing_rows | checked_rows | reported_turns | cost_usd | wall_min | bugs_checked | capture_samples |
|---|---|---|---|---|---|---|---|---|---|
| tier1 | bucket_clean | pass | 0 | 928 | 8 | 0.23 | 1.1 | 5 |  |
| tier1 | lock_clean | pass | 0 | 1017 | 11 | 0.35 | 1.7 | 8 |  |
| tier1 | handshake_capture | pass | 0 | 641 | 21 | 0.62 | 2.6 | 4 | 3268 |
| tier1 | cpu_clean | pass | 0 | 1251 | 14 | 0.59 | 3.1 | 7 |  |
| tier1 | lock_capture | pass | 0 | 1017 | 40 | 1.86 | 11.4 | 8 | 8415 |
| tier1 | cpu_capture | pass | 0 | 1251 | 125 | 10.39 | 68.8 | 7 | 6211 |
| tier2-run1 | cache_clean | pass | 0 | 1621 | 16 | 0.45 | 2.4 | 5 |  |
| tier2-run1 | crcrx_clean | pass | 0 | 3426 | 16 | 0.55 | 3.0 | 7 |  |
| tier2-run1 | crcrx_capture | fail | 208 | 3426 | 34 | 1.62 | 7.8 | 7 | 29007 |
| tier2-run1 | mcu_clean | pass | 0 | 2585 | 41 | 1.94 | 7.9 | 7 |  |
| tier2-run1 | mcu_capture | pass | 0 | 2585 | 1 | 14.86 | 57.2 | 7 | 28992 |
| tier2 | crcrx_clean | pass | 0 | 3426 | 14 | 0.47 | 2.3 | 8 |  |
| tier2 | crcrx_capture | pass | 0 | 3426 | 35 | 1.72 | 9.1 | 8 | 29007 |

13 runs, 12 pass, reported cost $35.65 (a cancelled first cpu_capture run is not counted).
