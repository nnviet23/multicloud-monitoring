# Experiment artifact layout

Use one directory per run:

```text
experiments/
  manifests/
    YYYYMMDD_teastore_<scenario>_runNN.yaml
  raw/
    YYYYMMDD_teastore_<scenario>_runNN/
      workload/
      metrics/
      logs/
      traces/
      system/
  processed/
    YYYYMMDD_teastore_<scenario>_runNN/
  reports/
    report_<topic>_<YYYYMMDD>.md
```

Rules:
- Raw files are immutable; processed outputs are regenerable.
- Every processed file records input run IDs, script/notebook version, and transformation parameters.
- Keep secrets and unredacted credentials out of all artifact directories.
- Use UTC timestamps in filenames/metadata.
- Document missing data and invalid runs instead of deleting them.
