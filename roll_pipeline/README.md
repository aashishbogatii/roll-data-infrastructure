# roll_pipeline

Ingests raw county assessor roll files (Excel/CSV), cleans them into a typed,
standardized schema, enriches each parcel with its coordinates/geometry and
building characteristics, and writes partitioned parquet that the lookup service
reads.

Runs the same locally (dev → local disk) or on AWS Lambda (prod → S3) by flipping
one environment variable.

## Quickstart (local)

Local is the default (`ENV=dev`)

```powershell
# 1. one-time: virtualenv + dependencies
python -m venv roll_pipeline/.venv
roll_pipeline/.venv/Scripts/pip install -r roll_pipeline/requirements.txt

# 2. (optional) point at your own data dirs; else the D:/roll_data defaults apply
$env:ROLL_SOURCE_DEV = "D:/roll_data"
$env:ROLL_OUTPUT_DEV = "D:/roll_data/clean"

# 3. build one county (the name must match a registry.yaml source)
roll_pipeline/.venv/Scripts/python -m roll_pipeline.runner sacramento
roll_pipeline/.venv/Scripts/python -m roll_pipeline.runner placer
#    ...or omit the name to build every source in the registry
roll_pipeline/.venv/Scripts/python -m roll_pipeline.runner

# 4. run the tests
roll_pipeline/.venv/Scripts/pytest -q roll_pipeline/tests
```

Each run logs `reading → read N rows → cleaned + validated → enriching → wrote`.
Rebuild a county whenever its transform or `registry.yaml` entry changes.


## Layout

| File | Purpose |
|------|---------|
| `config.py` | Picks source/output roots from `ENV` (dev = local, prod = S3). |
| `registry.yaml` | Source catalog — one entry per raw roll file. |
| `runner.py` | Orchestrator: read → clean → validate → enrich → write, per source. |
| `lambda_handler.py` | AWS Lambda entrypoint (`handler`). |
| `transforms/` | Per-county adapters: `sacramento_secured.py`, `sacramento_unsecured.py`, `sacramento_characteristics.py`, `sacramento_transfers.py`, `placer_secured.py`, and `tra_rates.py` (shared by both counties). |
| `parsers.py` | Vectorized column transforms (`col_int`, `col_float`, `col_str`, …). |
| `normalize.py` | Shared APN + address normalization. |
| `enrich.py` | `enrich_geometry` (lat/long/geometry), `enrich_characteristics` (building fields), and `enrich_transfers` (latest sale date/price), all by APN. |
| `writer.py` | Writes the cleaned DataFrame to partitioned parquet. |
| `requirements.txt` | Runtime dependencies. |
| `Dockerfile` | Container image for running the ingest on Lambda. |

## Configuration

All via environment variables (defaults in `config.py`):

| Variable | Meaning |
|----------|---------|
| `ENV` | Environment switch: `dev` → local disk, `prod` → S3. |
| `ROLL_SOURCE_DEV` | Raw source root for local (dev) runs. |
| `ROLL_SOURCE_PROD` | Raw source root for cloud (prod) runs. |
| `ROLL_OUTPUT_DEV` | Cleaned parquet output root for local (dev) runs. |
| `ROLL_OUTPUT_PROD` | Cleaned parquet output root for cloud (prod) runs. |

## How it works

The runner loops every source in `registry.yaml` and takes each one end to end:

1. **Resolve the path** — `config.py` picks the root from `ENV` (dev → local
   disk, prod → S3); `runner._resolve()` joins a relative registry path to that
   root. Absolute (`C:/…`) or `s3://…` paths override it per entry, so the same
   registry runs local or in the cloud.
2. **Read raw as text** — `_read_raw()` reads the xlsx/csv with `dtype=str` so
   codes keep their leading zeros (APN, tax-rate-area, etc.). xlsx uses the fast
   **calamine** engine.
3. **Clean + validate** — the per-county transform (`transforms/<name>.py`) maps
   raw columns to the canonical schema via its `FIELD_MAP`, derives the keys
   (`apn`, `apn_normalized`), the normalized `address`, and totals; `validate()`
   then checks the result.
4. **Enrich by APN** (secured only):
   - `enrich_geometry()` LEFT-joins `longitude`, `latitude`, and `geometry`
     (WKB → GeoJSON) from the parcel parquet.
   - `enrich_characteristics()` cleans the raw characteristics file in memory
     (`sacramento_characteristics.clean`) and LEFT-joins its building fields
     (`bedrooms`, `bathrooms`, `living_area_sqft`, …) — **adding only columns
     not already on the roll**, so it never overwrites roll fields. Nothing is
     persisted for characteristics; it's read, cleaned, and joined on the fly.
   - `enrich_transfers()` cleans the two-year transfer list in memory
     (`sacramento_transfers.clean`) and LEFT-joins the latest pre-cutoff sale
     per parcel (`last_sale_date`, `last_sale_price`, `is_group_sale`,
     `sale_group_id`, …), same add-only, join-on-the-fly pattern.
5. **Write** — `write_parquet()` sorts by `apn_normalized` and writes
   `OUTPUT_ROOT/<county>/<year>/<name>.parquet` in ~100k-row row groups, so a
   keyed lookup reads one row group instead of the whole file.

Every stage logs (`reading → read N rows → cleaned + validated → enriching →
wrote`). A source that fails is logged with its traceback and skipped; the rest
still run.

The join key is `apn_normalized` (alphanumerics only, uppercased) built by the
shared `normalize.py`, so the roll, the parcel file, and the characteristics file
all line up on the same key.

## Registry entry

```yaml
sources:
  - name: sacramento_2026_secured        # output basename
    roll_year: 2026
    path: sacramento/2026/secured_roll_public.xlsx   # relative to source root
    format: xlsx
    transform: sacramento_secured         # transforms/<name>.py
    parcels: sacramento/2026/sacramento_parcels.parquet   # optional: geometry
    characteristics:                      # optional: building fields, joined in memory
      path: sacramento/2026/Characteristics_roll_2026.xlsx
      format: xlsx
      transform: sacramento_characteristics
    transfers:                            # optional: latest sale per parcel, joined in memory
      path: sacramento/2026/Two-Year Transfer List 07.01.26.xlsx
      format: xlsx
      transform: sacramento_transfers
```

`parcels`, `characteristics`, and `transfers` are optional and apply to the
secured roll.

## Add a new source

1. Write `transforms/<county>_<rolltype>.py` with `COUNTY`, `ROLL_TYPE`,
   `EXPECTED_COLUMNS`, `FIELD_MAP`, and `clean()` / `validate()` — copy an
   existing transform.
2. Add an entry to `registry.yaml` pointing at the raw file and that transform.
3. Run the pipeline; the new source is picked up automatically.
