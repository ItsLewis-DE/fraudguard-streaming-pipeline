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
- Hive Metastore Thrift API: `thrift://localhost:9083`
- Spark master: `spark://localhost:7077`
- Spark worker UI: `http://localhost:8082`
- Spark master UI: `http://localhost:8083`

## Local data platform

The Compose stack creates a `fraud-lake` bucket in MinIO. Hive Metastore stores
table metadata in PostgreSQL, while table data uses the warehouse location
`s3a://fraud-lake/warehouse`. Spark is configured to use both the remote Hive
Metastore and MinIO through S3A.

The Hive and Spark images include their matching PostgreSQL/S3A dependencies;
their configuration files live under `docker/hive/conf/` and
`docker/spark/conf/`.

Open a Spark SQL session with:

```bash
docker compose exec spark-master \
  /opt/spark/bin/spark-sql --master spark://spark-master:7077
```

The MinIO and PostgreSQL credentials in `docker-compose.yml` are intended only
for local development. Replace them with secrets before using this stack in a
shared or production environment.

Publish a small smoke-test sample:

```bash
uv run python main.py --max-records 100 --events-per-second 20
```

The producer reads the Avro definitions from `schemas/` and registers them on
first use. With the default topic-name strategy, the subjects are
`fraud.transaction-value` and `fraud.transaction.label-value`. Messages use
Confluent's Avro wire format, so consumers should deserialize them through the
same Schema Registry. Global schema compatibility is configured as `BACKWARD`.

Override the Registry endpoint with either
`PAYSIM_SCHEMA_REGISTRY_URL` or `--schema-registry-url`:

```bash
uv run python main.py --schema-registry-url http://localhost:8081 --max-records 100
```

Publish the entire CSV at 1,000 transactions per second:

```bash
uv run python main.py --events-per-second 1000
```

Use `--events-per-second 0` for maximum throughput. The producer reads the CSV
one row at a time, so the full dataset is not loaded into memory.

Two records with the same `event_id` are produced for each CSV row:

- `fraud.transaction` contains transaction features and never contains labels.
- `fraud.transaction.label` contains `isFraud` and `isFlaggedFraud` for offline
  evaluation, monitoring, and delayed model feedback.

The label topic should not be available to the online inference consumer. In a
real system, labels should be emitted only after investigation, chargeback, or
another ground-truth process confirms the outcome.
