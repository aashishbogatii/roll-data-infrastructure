# roll_pipeline

Ingests raw county assessor roll files (Excel/CSV), cleans them into a typed,
standardized schema, optionally enriches each parcel with its coordinates and
geometry, and writes partitioned parquet that the lookup service reads.

Runs the same locally (dev → local disk) or on AWS Lambda (prod → S3) by flipping
one environment variable.

## Layout

| File | Purpose |
|------|---------|
| `config.py` | Picks source/output roots from `ENV` (dev = local, prod = S3). |
| `registry.yaml` | Source catalog — one entry per raw roll file. |
| `runner.py` | Orchestrator: read → clean → validate → enrich → write, per source. |
| `lambda_handler.py` | AWS Lambda entrypoint (`handler`). |
| `transforms/` | Per-county adapters (`sacramento_secured.py`, `sacramento_unsecured.py`). |
| `parsers.py` | Vectorized column transforms used by the transforms. |
| `normalize.py` | Shared APN + address normalization. |
| `enrich.py` | Adds longitude/latitude/geometry to the roll by APN. |
| `writer.py` | Writes the cleaned DataFrame to partitioned parquet. |
| `requirements.txt` | Runtime dependencies. |
| `Dockerfile` | Container image for running the ingest on Lambda. |

