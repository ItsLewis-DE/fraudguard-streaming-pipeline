# FraudGuard streaming pipeline

## Replay PaySim data to Kafka

Place the PaySim CSV at `data/data.csv`. The dataset is intentionally excluded
from Git because it is larger than GitHub's regular file-size limit.

Install the Python dependencies, then build and start the complete local stack:

```bash
uv sync
docker compose up -d --build
```

The local endpoints are:

- Kafka: `localhost:9092`
- Schema Registry REST API: `http://localhost:8081`
- Kafka UI: `http://localhost:8080`
- MinIO S3 API: `http://localhost:9000`
- MinIO Console: `http://localhost:9001`
- Spark master: `spark://localhost:7077`
- Spark worker UI: `http://localhost:8082`
- Spark master UI: `http://localhost:8083`

## Local data platform

Spark writes Parquet data and streaming checkpoints directly to MinIO through
S3A. It uses the in-memory Spark catalog, so the stack does not require an
external catalog service or metadata database.

Create the transaction and label buckets before starting the streaming jobs:

```bash
MINIO_ENDPOINT=http://localhost:9000 ./minIO/init_bucket.sh
```

The Spark image includes the required S3A dependencies; its configuration files
live under `docker/spark/conf/`.

Open a Spark SQL session with:

```bash
docker compose exec spark-master \
  /opt/spark/bin/spark-sql --master spark://spark-master:7077
```

The MinIO credentials in `docker-compose.yml` are intended only for local
development. Replace them with secrets before using this stack in a shared or
production environment.

Publish a small smoke-test sample:

```bash
uv run python producer/kafka_producer.py \
  --max-records 100 \
  --events-per-second 20
```

The producer reads the Avro definitions from `schemas/` and registers them on
first use. With the default topic-name strategy, the subjects are
`fraud.transaction-value` and `fraud.transaction.label-value`. Messages use
Confluent's Avro wire format, so consumers should deserialize them through the
same Schema Registry. Global schema compatibility is configured as `BACKWARD`.

Override the Registry endpoint with either
`PAYSIM_SCHEMA_REGISTRY_URL` or `--schema-registry-url`:

```bash
uv run python producer/kafka_producer.py \
  --schema-registry-url http://localhost:8081 \
  --max-records 100
```

Publish the entire CSV at 1,000 transactions per second:

```bash
uv run python producer/kafka_producer.py --events-per-second 1000
```

Use `--events-per-second 0` for maximum throughput. The producer reads the CSV
one row at a time, so the full dataset is not loaded into memory. It first
counts the rows in each PaySim `step`, then distributes their zero-based
ordinals across that step's 3,600,000 milliseconds:

```text
event_time = 2026-01-01T00:00:00Z
             + (step - 1) hours
             + floor(ordinal_within_step * 3,600,000 / rows_in_step) ms
```

The same source row therefore keeps the same `event_id` and `event_time` on
every replay. Only `ingested_at` reflects the current producer run. If a step
contains exactly 3,600 rows, ordinal 120 maps to an offset of 120 seconds.

Run the transaction Kafka-to-MinIO job from the read-only jobs directory
mounted into the Spark containers:

```bash
docker compose exec spark-master \
  /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --deploy-mode client \
  --conf spark.cores.max=1 \
  /opt/spark/jobs/event_kafka_minio.py
```

In a second terminal, run the independent label landing job:

```bash
docker compose exec spark-master \
  /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --deploy-mode client \
  --conf spark.cores.max=1 \
  /opt/spark/jobs/labels_kafka_minio.py
```

Both jobs share the Confluent wire-format, Schema Registry, Avro decoding,
checkpoint, replay, and quarantine implementation in
`spark/jobs/kafka_minio_landing.py`. They intentionally use separate topics,
contracts, output buckets, quarantine buckets, date partitions, and checkpoint
locations. Valid labels are written to `fraud-transaction-labels`, partitioned
by `observed_date`; rejected labels are written to
`fraud-transaction-labels-quarantine` with their original Kafka bytes.

Each job runs continuously. Stop it with `Ctrl+C`. The one-core limit lets both
jobs share the current two-core local Spark worker. Changes under `spark/jobs/`
are immediately visible in both Spark containers; restart the submitted job to
run the updated Python code. The version-pinned Kafka and Avro connector JARs
are included in the Spark image, so submitting the job does not contact Maven.

Two records with the same `event_id` are produced for each CSV row:

- `fraud.transaction` contains transaction features and never contains labels.
- `fraud.transaction.label` contains `isFraud` and `isFlaggedFraud` for offline
  evaluation, monitoring, and delayed model feedback.

The label topic should not be available to the online inference consumer. In a
real system, labels should be emitted only after investigation, chargeback, or
another ground-truth process confirms the outcome.

## Schema Registry integration test

With Kafka and Schema Registry running through Docker Compose, run:

```bash
RUN_SCHEMA_REGISTRY_INTEGRATION=1 \
uv run python -m unittest -v \
tests.integration.test_schema_registry_evolution
```

The test creates an isolated Kafka topic and Schema Registry subject, sends one
Avro v1 message and one compatible v2 message, and reads both with the v2 reader
schema. It also verifies that an incompatible schema is rejected with HTTP 409.
The temporary topic and subject are removed after the test.

To keep the generated topic and subject for manual inspection, run the test
with `KEEP_SCHEMA_TEST_RESOURCES=1`. The test prints their names and both schema
IDs:

```bash
RUN_SCHEMA_REGISTRY_INTEGRATION=1 \
KEEP_SCHEMA_TEST_RESOURCES=1 \
uv run python -m unittest -v \
tests.integration.test_schema_registry_evolution
```
