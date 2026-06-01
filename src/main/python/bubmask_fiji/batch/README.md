# Batch Layer

Runs BubMask-Fiji over a folder or CSV manifest of TIFF images with one run
folder per image, resume/retry behavior, combined measurements, combined
histograms, and experiment-level summaries.

Default model:

```text
models/bubmask-maskrcnn-unsw-round3-v1
```

Example:

```powershell
cd C:\Users\arman\tor_mere\bubmask-fiji
.\.venv-bubmask\Scripts\python.exe .\src\main\python\bubmask_fiji\batch\run_batch.py `
  --input-dir .\validation\real_tiff_samples `
  --output-dir .\validation\phase8_round3_batch `
  --px-per-mm 183
```

Outputs:

- `batch_manifest.csv`;
- `batch_progress.log`;
- one numbered run folder per image;
- `combined_per_bubble_measurements.csv`;
- `combined_diameter_histogram_all.csv` / `.png`;
- `combined_diameter_histogram_accepted.csv` / `.png`;
- `combined_diameter_histogram_raw_vs_reconstructed.csv` / `.png`;
- `experiment_summary.csv`;
- `batch_summary.json`.

Resume behavior is on by default. Existing successful run folders are skipped
unless `--force` or `--no-resume` is supplied.
