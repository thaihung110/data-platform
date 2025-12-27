"""
PySpark application to ingest NYC taxi trip data into Iceberg bronze table.

This job:
1. Reads raw Parquet files from MinIO raw bucket (raw/taxi/upload_id=.../chunk_*.parquet)
2. Cleans and transforms the data (including deduplication)
3. Loads data into Iceberg table in bronze warehouse on lakekeeper
"""

import os
import sys
from functools import reduce

from pyspark import SparkConf
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    col,
    current_timestamp,
    isnan,
    isnull,
    regexp_replace,
    to_timestamp,
    trim,
    upper,
    when,
)
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)


def get_spark_session():
    """Create and configure Spark session with Iceberg and lakekeeper catalog."""

    # Get configuration from environment variables
    spark_minor_version = os.getenv("SPARK_MINOR_VERSION", "3.5")
    iceberg_version = os.getenv(
        "ICEBERG_VERSION", "1.5.2"
    )  # Upgrade to fix OAuth2 bugs
    catalog_url = os.getenv(
        "CATALOG_URL", "http://openhouse-lakekeeper:8181/catalog"
    )
    client_id = os.getenv("CLIENT_ID", "spark")
    client_secret = os.getenv(
        "CLIENT_SECRET", "3FfkvrupMYsojoT2RnXqknvjCsljwFWl"
    )
    warehouse = os.getenv("WAREHOUSE", "bronze")
    keycloak_token_endpoint = os.getenv(
        "KEYCLOAK_TOKEN_ENDPOINT",
        "http://openhouse-keycloak:80/realms/iceberg/protocol/openid-connect/token",
    )

    # Spark configuration for Iceberg and lakekeeper
    # Note: S3/MinIO configs are set in Spark Operator YAML via hadoopConf and AWS env vars
    # Note: spark.jars.packages is also set in YAML to ensure JARs are available before SparkSession
    conf = {
        "spark.sql.extensions": "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        "spark.sql.catalog.lakekeeper": "org.apache.iceberg.spark.SparkCatalog",
        "spark.sql.catalog.lakekeeper.type": "rest",
        "spark.sql.catalog.lakekeeper.uri": catalog_url,
        "spark.sql.catalog.lakekeeper.credential": f"{client_id}:{client_secret}",
        "spark.sql.catalog.lakekeeper.warehouse": warehouse,
        "spark.sql.catalog.lakekeeper.scope": "lakekeeper",
        "spark.sql.catalog.lakekeeper.oauth2-server-uri": keycloak_token_endpoint,
        # CRITICAL: Disable vectorized Parquet reader to avoid FLOAT->DOUBLE conversion errors
        # Vectorized reader is strict about type conversions and fails on FLOAT->DOUBLE
        # Row-based reader is more flexible and can handle type differences
        "spark.sql.parquet.enableVectorizedReader": "false",
        # "spark.sql.adaptive.enabled": "true",
        # "spark.sql.adaptive.coalescePartitions.enabled": "true",
    }

    # Create Spark session via SparkConf (so JARs/configs are applied before creation)
    spark_conf = SparkConf().setAppName("NYC Taxi Data Ingestion")
    for key, value in conf.items():
        spark_conf = spark_conf.set(key, value)
    spark = SparkSession.builder.config(conf=spark_conf).getOrCreate()

    return spark


def main():
    """Main function to orchestrate the ETL process."""
    try:
        # Get input path from command line arguments or use default
        # Default path reads all parquet files from raw/taxi/ bucket
        input_path = (
            sys.argv[1] if len(sys.argv) > 1 else "s3a://raw/taxi/*/*.parquet"
        )
        database = sys.argv[2] if len(sys.argv) > 2 else "bronze"
        table = sys.argv[3] if len(sys.argv) > 3 else "taxi_trips"

        print("=" * 60)
        print("NYC Taxi Data Ingestion Job - Raw to Bronze")
        print("=" * 60)
        print(f"Input path: {input_path}")
        print(f"Target: lakekeeper.{database}.{table}")
        print("=" * 60)

        # Initialize Spark session
        spark = get_spark_session()

        # Read raw Parquet data from MinIO
        print(f"Reading Parquet files from MinIO: {input_path}")
        # ULTIMATE FIX: Read each Parquet file INDIVIDUALLY with its own schema,
        # convert to STRING immediately, then union all files together.
        # This prevents "Parquet column cannot be converted" errors that happen
        # when Spark tries to read files with incompatible types (FLOAT vs DOUBLE)

        print("Discovering Parquet files to read individually...")
        # Use Hadoop FileSystem API to list all Parquet files
        hadoop_conf = spark.sparkContext._jsc.hadoopConfiguration()
        jvm = spark.sparkContext._jvm

        # Parse the input path to handle glob patterns
        java_path = jvm.org.apache.hadoop.fs.Path(input_path)
        fs = java_path.getFileSystem(hadoop_conf)

        # Get all matching files
        file_statuses = fs.globStatus(java_path)

        if file_statuses is None or len(file_statuses) == 0:
            raise ValueError(f"No Parquet files found at {input_path}")

        print(f"Found {len(file_statuses)} file/directory path(s)")

        # Collect all Parquet files (handle both files and directories)
        parquet_files = []
        for file_status in file_statuses:
            file_path = str(file_status.getPath())
            if file_status.isDirectory():
                # List files in directory
                dir_files = fs.listStatus(
                    jvm.org.apache.hadoop.fs.Path(file_path)
                )
                for dir_file in dir_files:
                    dir_file_path = str(dir_file.getPath())
                    if dir_file_path.endswith(".parquet"):
                        parquet_files.append(dir_file_path)
            elif file_path.endswith(".parquet"):
                parquet_files.append(file_path)

        if not parquet_files:
            raise ValueError(f"No .parquet files found at {input_path}")

        print(f"Found {len(parquet_files)} Parquet file(s) to process")

        # Read each file individually, convert to STRING, then union
        all_string_dfs = []
        for i, parquet_file in enumerate(parquet_files):
            print(f"Reading file {i+1}/{len(parquet_files)}: {parquet_file}")
            try:
                # Read single file with its own schema (no merging with other files)
                file_df = spark.read.parquet(parquet_file)

                # Immediately convert ALL columns to STRING to avoid type conflicts
                string_exprs = []
                for field in file_df.schema.fields:
                    string_exprs.append(
                        f"CAST(`{field.name}` AS STRING) AS `{field.name}`"
                    )

                string_df = file_df.selectExpr(*string_exprs)
                all_string_dfs.append(string_df)

                row_count = file_df.count()
                print(f"  ✓ Converted {row_count} rows to STRING schema")

            except Exception as e:
                print(f"  ✗ Failed to read {parquet_file}: {str(e)}")
                # Continue with other files
                continue

        if not all_string_dfs:
            raise ValueError("No Parquet files could be read successfully")

        # Union all string DataFrames
        print(
            f"Unioning {len(all_string_dfs)} DataFrames with STRING schema..."
        )
        normalized_df = reduce(DataFrame.unionByName, all_string_dfs)

        print("All files merged with STRING schema - now safe to process:")
        normalized_df.printSchema()

        # Count records after normalization
        source_count = normalized_df.count()
        print(
            f"Read {source_count} records from {input_path} (after schema normalization)"
        )

        # Register as temp view for SQL transformation
        normalized_df.createOrReplaceTempView("raw_taxi")

        # Transform and clean data using Spark SQL
        # NOTE: All columns are STRING now, so we need to cast to numeric types first
        # before using functions like GREATEST that require type matching
        # Using FLOAT instead of DOUBLE to match source data and avoid conversion issues
        print("Transforming and cleaning data...")
        spark.sql(
            """
            CREATE OR REPLACE TEMP VIEW cleaned_taxi AS
            SELECT
                CAST(COALESCE(VendorID, '-1') AS INT) AS vendor_id,
                to_timestamp(tpep_pickup_datetime, 'yyyy-MM-dd HH:mm:ss') AS pickup_datetime,
                to_timestamp(tpep_dropoff_datetime, 'yyyy-MM-dd HH:mm:ss') AS dropoff_datetime,
                CAST(GREATEST(COALESCE(CAST(passenger_count AS INT), 0), 0) AS INT) AS passenger_count,
                CAST(GREATEST(COALESCE(CAST(trip_distance AS FLOAT), 0.0), 0.0) AS FLOAT) AS trip_distance,
                CAST(COALESCE(RatecodeID, '-1') AS INT) AS rate_code_id,
                UPPER(TRIM(COALESCE(store_and_fwd_flag, 'N'))) AS store_and_fwd_flag,
                CAST(COALESCE(PULocationID, '-1') AS INT) AS pu_location_id,
                CAST(COALESCE(DOLocationID, '-1') AS INT) AS do_location_id,
                CAST(COALESCE(payment_type, '-1') AS INT) AS payment_type,
                CAST(COALESCE(CAST(fare_amount AS FLOAT), 0.0) AS FLOAT) AS fare_amount,
                CAST(COALESCE(CAST(extra AS FLOAT), 0.0) AS FLOAT) AS extra,
                CAST(COALESCE(CAST(mta_tax AS FLOAT), 0.0) AS FLOAT) AS mta_tax,
                CAST(COALESCE(CAST(tip_amount AS FLOAT), 0.0) AS FLOAT) AS tip_amount,
                CAST(COALESCE(CAST(tolls_amount AS FLOAT), 0.0) AS FLOAT) AS tolls_amount,
                CAST(COALESCE(CAST(improvement_surcharge AS FLOAT), 0.0) AS FLOAT) AS improvement_surcharge,
                CAST(COALESCE(CAST(total_amount AS FLOAT), 0.0) AS FLOAT) AS total_amount,
                CAST(COALESCE(CAST(congestion_surcharge AS FLOAT), 0.0) AS FLOAT) AS congestion_surcharge,
                current_timestamp() AS ingestion_timestamp
            FROM raw_taxi
            WHERE tpep_pickup_datetime IS NOT NULL 
                AND tpep_dropoff_datetime IS NOT NULL
            """
        )

        # Deduplicate data based on key columns
        print("Deduplicating data...")
        spark.sql(
            """
            CREATE OR REPLACE TEMP VIEW deduped_taxi AS
            SELECT *
            FROM (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY 
                            pickup_datetime, 
                            dropoff_datetime,
                            pu_location_id,
                            do_location_id,
                            vendor_id
                        ORDER BY ingestion_timestamp DESC
                    ) AS row_num
                FROM cleaned_taxi
            ) tmp
            WHERE row_num = 1
            """
        )

        deduped_count = spark.sql(
            "SELECT COUNT(*) AS cnt FROM deduped_taxi"
        ).collect()[0]["cnt"]
        duplicates_removed = source_count - deduped_count
        print(
            f"After deduplication: {deduped_count} records (removed {duplicates_removed} duplicates)"
        )

        # Create namespace if not exists
        spark.sql(f"CREATE NAMESPACE IF NOT EXISTS lakekeeper.{database}")
        print(f"Created/verified namespace lakekeeper.{database}")

        # Check if table exists
        table_exists = spark.catalog.tableExists(
            f"lakekeeper.{database}.{table}"
        )

        if not table_exists:
            # Create table for the first time
            print(f"Creating new table lakekeeper.{database}.{table}")
            spark.sql(
                f"""
                CREATE TABLE lakekeeper.{database}.{table}
                USING iceberg
                PARTITIONED BY (days(pickup_datetime))
                TBLPROPERTIES (
                    'format-version'='2',
                    'write.parquet.compression-codec'='snappy'
                )
                AS SELECT * FROM (
                    SELECT * FROM deduped_taxi WHERE row_num = 1
                ) final
                """
            )
            print(f"Created table lakekeeper.{database}.{table}")
        else:
            # Table exists, use MERGE INTO for upsert
            print(f"Table exists, performing MERGE INTO for upsert...")
            spark.sql(
                f"""
                MERGE INTO lakekeeper.{database}.{table} AS target
                USING (
                    SELECT * FROM deduped_taxi WHERE row_num = 1
                ) AS source
                ON target.pickup_datetime = source.pickup_datetime
                    AND target.dropoff_datetime = source.dropoff_datetime
                    AND target.pu_location_id = source.pu_location_id
                    AND target.do_location_id = source.do_location_id
                    AND target.vendor_id = source.vendor_id
                WHEN MATCHED THEN 
                    UPDATE SET *
                WHEN NOT MATCHED THEN 
                    INSERT *
                """
            )
            print(f"Merged data into lakekeeper.{database}.{table}")

        # Verify final row count
        result_count = spark.sql(
            f"SELECT COUNT(*) AS cnt FROM lakekeeper.{database}.{table}"
        ).collect()[0]["cnt"]
        print(f"Total records in lakekeeper.{database}.{table}: {result_count}")

        print("=" * 60)
        print("Job completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"Error occurred: {str(e)}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)

    finally:
        if "spark" in locals():
            spark.stop()


if __name__ == "__main__":
    main()
