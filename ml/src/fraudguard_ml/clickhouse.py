from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import clickhouse_connect


@dataclass(frozen=True)
class ClickHouseSettings:
    host: str
    port: int
    username: str
    database: str
    secure: bool
    password: str = field(repr=False)

    @classmethod
    def from_env(cls) -> ClickHouseSettings:
        password = os.getenv("CLICKHOUSE_ML_PASSWORD")
        if not password:
            raise ValueError("CLICKHOUSE_ML_PASSWORD must be set")

        port_text = os.getenv("CLICKHOUSE_ML_PORT", "8123")
        try:
            port = int(port_text)
        except ValueError as exc:
            raise ValueError("CLICKHOUSE_ML_PORT must be an integer") from exc
        if not 1 <= port <= 65535:
            raise ValueError("CLICKHOUSE_ML_PORT must be between 1 and 65535")

        secure_text = os.getenv("CLICKHOUSE_ML_SECURE", "false").lower()
        if secure_text not in {"true", "false"}:
            raise ValueError("CLICKHOUSE_ML_SECURE must be true or false")

        username = os.getenv(
            "CLICKHOUSE_ML_USER",
            "fraudguard_ml_reader",
        )
        if username != "fraudguard_ml_reader":
            raise ValueError("ML validator must use fraudguard_ml_reader")

        return cls(
            host=os.getenv("CLICKHOUSE_ML_HOST", "localhost"),
            port=port,
            username=username,
            password=password,
            database=os.getenv(
                "CLICKHOUSE_ML_DATABASE",
                "fraudguard",
            ),
            secure=secure_text == "true",
        )


def create_clickhouse_client(settings: ClickHouseSettings) -> Any:
    return clickhouse_connect.get_client(
        host=settings.host,
        port=settings.port,
        username=settings.username,
        password=settings.password,
        database=settings.database,
        secure=settings.secure,
        settings={"readonly": 1},  # Cái này để cho clickhouse
    )
