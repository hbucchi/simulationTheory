# Data for the session-2 debate

All files are produced by the scripts in this folder on commit `69d36a5` (200 agents, 270 days).

| File | Script | What it is |
|---|---|---|
| `d_<run>.json` | `scen2.py` (all runs: `run_all.sh`) | A row every 30 days for each scenario in the evidence pack |
| `sp_baseline.json`, `sp_light.json` | `spend.py` | Government spending by category over 270 days (Round 3) |
| `pa_baseline.json`, `pa_light.json` | `participation.py` | Where labour capacity goes at day 45 and day 270 (Round 7) |

The needs breakdown in Round 1 (boredom 181, health 167, ...) came from a one-off check on the seed-11 baseline: count the agents whose need is above `rules.seek_threshold` at day 270.
Re-run everything with `./run_all.sh` (about 4 minutes on 4 cores).
