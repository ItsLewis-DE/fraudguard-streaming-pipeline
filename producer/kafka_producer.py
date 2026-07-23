from __future__ import annotations

import argparse
import csv
import logging
import os
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Mapping

from confluent_kafka import Message, Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "data.csv"
DEFAULT_SCHEMA_REGISTRY_URL = "http://localhost:8081"
TRANSACTION_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "fraud_transaction.avsc"
LABEL_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "fraud_transaction_label.avsc"

REPLAY_EPOCH = datetime(2026,1,1,tzinfo=timezone.utc)
REPLAY_EPOCH_MS = int(REPLAY_EPOCH.timestamp() * 1000)
STEP_DURATION_MS = 60*60*1000

LOGGER = logging.getLogger("paysim-producer")

REQUIRED_COLUMNS = {
    "step",
    "type",
    "amount",
    "nameOrig",
    "oldbalanceOrg",
    "newbalanceOrig",
    "nameDest",
    "oldbalanceDest",
    "newbalanceDest",
    "isFraud",
    "isFlaggedFraud",
}


@dataclass
class DeliveryStats:
    delivered: int = 0
    failed: int = 0

    def callback(self, error: object, message: Message) -> None:
        if error is not None:
            self.failed += 1
            LOGGER.error(
                "Delivery failed: topic=%s key=%r error=%s",
                message.topic(),
                message.key(),
                error,
            )
            return
        self.delivered += 1


class RateLimiter:
    """Limit transaction pairs per second, not individual Kafka messages."""

    def __init__(self, events_per_second: float) -> None:
        self.interval = 0.0 if events_per_second <= 0 else 1.0 / events_per_second
        self.next_send_at = time.monotonic()

    def wait(self) -> None:
        if self.interval == 0:
            return

        self.next_send_at += self.interval
        delay = self.next_send_at - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        elif delay < -self.interval:
            # Do not try to catch up with a large burst after a long pause.
            self.next_send_at = time.monotonic()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay PaySim CSV transactions into Kafka."
    )
    parser.add_argument(
        "--data-path",
        type=Path,
        default=Path(os.getenv("PAYSIM_CSV_PATH", DEFAULT_DATA_PATH)),
    )
    parser.add_argument(
        "--bootstrap-servers",
        default=os.getenv("PAYSIM_KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
    )
    parser.add_argument(
        "--schema-registry-url",
        default=os.getenv(
            "PAYSIM_SCHEMA_REGISTRY_URL", DEFAULT_SCHEMA_REGISTRY_URL
        ),
    )
    parser.add_argument(
        "--transaction-topic",
        default=os.getenv("PAYSIM_KAFKA_TRANSACTION_TOPIC", "fraud.transaction"),
    )
    parser.add_argument(
        "--label-topic",
        default=os.getenv("PAYSIM_KAFKA_LABEL_TOPIC", "fraud.transaction.label"),
    )
    parser.add_argument(
        "--events-per-second",
        type=float,
        default=float(os.getenv("PAYSIM_EVENTS_PER_SECOND", "100")),
        help="Transactions per second; use 0 for maximum throughput (default: 100).",
    )
    parser.add_argument(
        "--skip-rows",
        type=int,
        default=0,
        help="Skip data rows before publishing; useful when resuming a replay.",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Stop after this many transactions; useful for smoke tests.",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=10_000,
        help="Log progress after this many transactions.",
    )
    return parser.parse_args()


def build_producer(bootstrap_servers: str) -> Producer:
    return Producer(
        {
            "bootstrap.servers": bootstrap_servers,
            "client.id": "paysim-csv-producer",
            "acks": "all", #Kafka chỉ xác nhận message khi tất cả các replica đã ghi message
            "enable.idempotence": True, #Bật tính năng này để tránh producer gửi trùng dữ liệu
            "retries": 2_147_483_647, 
            "max.in.flight.requests.per.connection": 5,
            "compression.type": "snappy",
            "linger.ms": 20, #thêm một độ trễ tối đa vào lô message
            "batch.num.messages": 10_000,
            "delivery.timeout.ms": 120_000,
        }
    )


def build_serializers(
    schema_registry_url: str,
) -> tuple[AvroSerializer, AvroSerializer]:
    """Create serializers that register each topic-value schema on first use."""
    registry = SchemaRegistryClient({"url": schema_registry_url})
    config = {"auto.register.schemas": True}
    transaction_serializer = AvroSerializer(
        registry,
        TRANSACTION_SCHEMA_PATH.read_text(encoding="utf-8"),
        conf=config,
    )
    label_serializer = AvroSerializer(
        registry,
        LABEL_SCHEMA_PATH.read_text(encoding="utf-8"),
        conf=config,
    )
    return transaction_serializer, label_serializer

def count_rows_per_step(data_path:str) -> Counter[int]:
    counts: Counter[int] = Counter() 
    with data_path.open("rb") as csv_file:
        raw_header = csv_file.readline() 
        if not raw_header:
            raise ValueError("file CSV rỗng!")
        header = next(csv.reader([raw_header.decode("utf-8")]))
        validate_header(header)
        step_index = header.index("step")
        for row_number,raw_row in enumerate(csv_file,start=1):
            if not raw_row.strip():
                continue 
            columns = raw_row.split(b",")
            try:
                step = int(columns[step_index])
            except (IndexError, ValueError) as error:
                raise ValueError(
                    f"Invalid step at CSV data row {row_number}"
                ) from error
            if step < 1:
                raise ValueError(f"PaySim step must be >= 1, got {step}")
            counts[step] += 1
    if not counts:
        raise ValueError("CSV contains no data rows")
    return counts 

def deterministic_event_time_ms(
    *,
    step: int,
    ordinal_within_step: int,
    rows_in_step: int,
) -> int:
    """Distribute a row deterministically inside its one-hour PaySim step."""
    if step < 1:
        raise ValueError(f"PaySim step must be >= 1, got {step}")
    if rows_in_step < 1:
        raise ValueError("rows_in_step must be >= 1")
    if not 0 <= ordinal_within_step < rows_in_step:
        raise ValueError(
            "ordinal_within_step must be between 0 and rows_in_step - 1"
        )

    offset_ms = ordinal_within_step * STEP_DURATION_MS // rows_in_step
    return REPLAY_EPOCH_MS + (step - 1) * STEP_DURATION_MS + offset_ms

def validate_header(fieldnames: list[str] | None) -> None:
    actual = set(fieldnames or [])
    missing = REQUIRED_COLUMNS - actual
    if missing:
        raise ValueError(f"CSV is missing required columns: {sorted(missing)}")

def convert_paysim_row(
    row: Mapping[str, str],
    row_number: int,
    *,
    ordinal_within_step: int,
    rows_in_step: int,
) -> tuple[dict[str, object], dict[str, object]]:
    
    event_id = f"paysim-{row_number:010d}"
    ingested_at = int(time.time() * 1000)
    step = int(row["step"])
    event_time = deterministic_event_time_ms(
        step=step,
        ordinal_within_step=ordinal_within_step,
        rows_in_step=rows_in_step,
    )

    event = {
        "event_id": event_id,
        "source": "paysim",
        "event_time": event_time,
        "ingested_at": ingested_at,
        "step":step,
        "type": row["type"],
        "amount": float(row["amount"]),
        "nameOrig": row["nameOrig"],
        "oldbalanceOrg": float(row["oldbalanceOrg"]),
        "newbalanceOrig": float(row["newbalanceOrig"]),
        "nameDest": row["nameDest"],
        "oldbalanceDest": float(row["oldbalanceDest"]),
        "newbalanceDest": float(row["newbalanceDest"]),
    }
    label = {
        "event_id": event_id,
        "source": "paysim",
        "observed_at": ingested_at,
        "isFraud": int(row["isFraud"]),
        "isFlaggedFraud": int(row["isFlaggedFraud"]),
    }
    return event, label


def serialize_avro(
    serializer: AvroSerializer,
    topic: str,
    payload: Mapping[str, object],
) -> bytes:
    value = serializer(
        payload,
        SerializationContext(topic, MessageField.VALUE),
    )
    if value is None:
        raise ValueError("Avro serializer returned no value")
    return value


def produce_with_backpressure(
    producer: Producer,
    *,
    topic: str,
    key: str,
    value: bytes,
    stats: DeliveryStats,
) -> None:
    while True:
        try:
            producer.produce(
                topic=topic,
                key=key,
                value=value,
                headers={
                    "content-type": "application/vnd.apache.avro+binary"
                },
                on_delivery=stats.callback,
            )
            return
        except BufferError:
            producer.poll(0.1)


def replay_csv(
    *,
    producer: Producer,
    data_path: Path,
    transaction_topic: str,
    label_topic: str,
    transaction_serializer: AvroSerializer,
    label_serializer: AvroSerializer,
    events_per_second: float,
    skip_rows: int,
    max_records: int | None,
    log_every: int,
) -> tuple[int, DeliveryStats]:
    if skip_rows < 0:
        raise ValueError("--skip-rows must be >= 0")
    if events_per_second < 0:
        raise ValueError("--events-per-second must be >= 0")
    if max_records is not None and max_records <= 0:
        raise ValueError("--max-records must be > 0")
    if log_every <= 0:
        raise ValueError("--log-every must be > 0")
    if not data_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {data_path}")

    stats = DeliveryStats()
    limiter = RateLimiter(events_per_second)
    rows_per_step = count_rows_per_step(data_path)
    ordinals_by_step: Counter[int] = Counter()
    published = 0
    started_at = time.monotonic()

    with data_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        validate_header(reader.fieldnames)

        for row_number, row in enumerate(reader, start=1):
            step = int(row["step"])
            ordinals_within_step = ordinals_by_step[step]
            ordinals_by_step[step]+=1
            if row_number <= skip_rows:
                continue
            if max_records is not None and published >= max_records:
                break

            event, label = convert_paysim_row(row, row_number,ordinal_within_step=ordinals_within_step,rows_in_step=rows_per_step[step])
            event_id = str(event["event_id"])
            event_value = serialize_avro(
                transaction_serializer,
                transaction_topic,
                event,
            )
            label_value = serialize_avro(
                label_serializer,
                label_topic,
                label,
            )
            produce_with_backpressure(
                producer,
                topic=transaction_topic,
                key=event_id,
                value=event_value,
                stats=stats,
            )
            produce_with_backpressure(
                producer,
                topic=label_topic,
                key=event_id,
                value=label_value,
                stats=stats,
            )

            producer.poll(0)
            published += 1
            if published % log_every == 0:
                elapsed = max(time.monotonic() - started_at, 0.001)
                LOGGER.info(
                    "Published %s transactions (%.1f transactions/s)",
                    f"{published:,}",
                    published / elapsed,
                )
            limiter.wait()

    outstanding = producer.flush(30)
    if outstanding:
        raise RuntimeError(f"Timed out with {outstanding} Kafka messages still queued")
    if stats.failed:
        raise RuntimeError(f"Kafka failed to deliver {stats.failed} messages")

    return published, stats


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()
    producer = build_producer(args.bootstrap_servers)
    transaction_serializer, label_serializer = build_serializers(
        args.schema_registry_url
    )

    LOGGER.info(
        "Replaying %s to %s and %s via %s (Schema Registry: %s)",
        args.data_path,
        args.transaction_topic,
        args.label_topic,
        args.bootstrap_servers,
        args.schema_registry_url,
    )
    try:
        published, stats = replay_csv(
            producer=producer,
            data_path=args.data_path,
            transaction_topic=args.transaction_topic,
            label_topic=args.label_topic,
            transaction_serializer=transaction_serializer,
            label_serializer=label_serializer,
            events_per_second=args.events_per_second,
            skip_rows=args.skip_rows,
            max_records=args.max_records,
            log_every=args.log_every,
        )
    except KeyboardInterrupt:
        LOGGER.warning("Interrupted; flushing queued messages before exit")
        producer.flush(10)
        return

    LOGGER.info(
        "Done: %s transactions and %s Kafka messages delivered",
        f"{published:,}",
        f"{stats.delivered:,}",
    )


if __name__ == "__main__":
    main()
