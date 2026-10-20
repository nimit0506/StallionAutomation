# Results

Everything here comes from the scripts in `scripts/`. Nothing was edited by hand.

| Folder | What it is |
|---|---|
| `clean_repo_rerun/` | Flight logs from the cleaned repo, reproduced with the commands below. This is what the current code produces. |
| `deck_run/` | Flight logs from the earlier run that the slides in `docs/` were made from. Kept so the slides can be traced. |
| `images/` | Five renders of the model (`iso`, `top`, `side`, `front`, `rear`), from `scripts/render_sim_images.sh`. |
| `mesh/` | `mesh_check_before.txt` (raw GLB, 28 of 96 parts need repair), `mesh_check_after.txt` (repaired, 96 of 96 clean), `mass.json` (mass, CG and inertia). |

## Commands that produced the logs

```bash
scripts/run_headless_test.sh --csv results/clean_repo_rerun/hover_log.csv
scripts/run_headless_test.sh --transition --climb-time 30 --climb-throttle 1800 \
    --csv results/clean_repo_rerun/transition_log.csv
```

The 10 Hz CSV columns are documented in `docs/CODE_GUIDE.md`, section 7.

## Summary

| Test | Result |
|---|---|
| Hover, clean re-run | PASS (max altitude 3.85 m, max tilt 10.6°). Still landing when the 15 s window ended. |
| Transition, clean re-run | Forward flight PASS (20.1 m/s, min altitude 16.6 m, max tilt 7.0°). Landed. |
| Mesh | 96 of 96 parts clean after repair. |
| Mass | 2451 g, CG 60 mm aft of the wing-root leading edge. Estimate: printed mass is assumed, not weighed. |

The hover verdict does not check landing; see section 7 of the guide.
