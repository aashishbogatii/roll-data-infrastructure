"""Pipeline config: dev -> local disk, prod -> S3.

Relative registry paths resolve against SOURCE_ROOT; absolute or s3:// paths in
the registry are used as-is.
"""

import os

# Environment switch: dev -> local disk, prod -> S3.
ENV = os.getenv("ENV", "dev").lower()

# Raw roll source files (where the registry's relative paths live).
DEV_SOURCE = os.getenv("ROLL_SOURCE_DEV", "D:/roll_data")
PROD_SOURCE = os.getenv("ROLL_SOURCE_PROD", "s3://ca-counties-roll-data/raw")
SOURCE_ROOT = (PROD_SOURCE if ENV == "prod" else DEV_SOURCE).rstrip("/")

# Cleaned parquet output.
DEV_OUTPUT = os.getenv("ROLL_OUTPUT_DEV", "D:/roll_data/clean")
PROD_OUTPUT = os.getenv("ROLL_OUTPUT_PROD", "s3://ca-counties-roll-data/curated")
OUTPUT_ROOT = (PROD_OUTPUT if ENV == "prod" else DEV_OUTPUT).rstrip("/")

IS_S3 = SOURCE_ROOT.startswith("s3://")
