# Local Artifacts

This folder is for generated local artifacts that are useful for audit or
handoff, but should not be treated as source code.

Current local archive folders:

- `results_archive_20260601/`: historical Fiji run folders moved out of the
  clean `results/` runtime directory.
- `training_runs_archive_20260601/`: historical training checkpoints and logs
  moved out of the clean `training_runs/` directory.

These files are intentionally ignored by git because they are large, generated,
and may include research-controlled data.
