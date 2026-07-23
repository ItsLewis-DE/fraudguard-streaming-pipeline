#!/usr/bin/env bash
set -euo pipefail

: "${CLICKHOUSE_LOADER_PASSWORD:?CLICKHOUSE_LOADER_PASSWORD must be set}"
: "${CLICKHOUSE_TRANSFORMER_PASSWORD:?CLICKHOUSE_TRANSFORMER_PASSWORD must be set}"
: "${CLICKHOUSE_SUPERSET_PASSWORD:?CLICKHOUSE_SUPERSET_PASSWORD must be set}"

#Không dùng echo vì echo sẽ gây thêm dấu \n, awk để tách chuỗi theo khoản trắng và chỉ lấy chuỗi đầu tiên
sha256_hash() {
    printf '%s' "$1" | sha256sum | awk '{print $1}'
}

loader_hash="$(sha256_hash "${CLICKHOUSE_LOADER_PASSWORD}")"
transformer_hash="$(sha256_hash "${CLICKHOUSE_TRANSFORMER_PASSWORD}")"
superset_hash="$(sha256_hash "${CLICKHOUSE_SUPERSET_PASSWORD}")"

client_args=(--multiquery)
if [[ -n "${CLICKHOUSE_USER:-}" ]]; then
    client_args+=(--user "${CLICKHOUSE_USER}")
fi
if [[ -n "${CLICKHOUSE_PASSWORD:-}" ]]; then
    client_args+=(--password "${CLICKHOUSE_PASSWORD}")
fi

clickhouse-client "${client_args[@]}" <<SQL
CREATE USER IF NOT EXISTS fraudguard_loader
IDENTIFIED WITH sha256_hash BY '${loader_hash}';

ALTER USER fraudguard_loader
IDENTIFIED WITH sha256_hash BY '${loader_hash}';

GRANT fraudguard_loader_role TO fraudguard_loader;
ALTER USER fraudguard_loader DEFAULT ROLE fraudguard_loader_role;

CREATE USER IF NOT EXISTS fraudguard_transformer
IDENTIFIED WITH sha256_hash BY '${transformer_hash}';

ALTER USER fraudguard_transformer
IDENTIFIED WITH sha256_hash BY '${transformer_hash}';

GRANT fraudguard_transformer_role TO fraudguard_transformer;
ALTER USER fraudguard_transformer DEFAULT ROLE fraudguard_transformer_role;

CREATE USER IF NOT EXISTS fraudguard_superset
IDENTIFIED WITH sha256_hash BY '${superset_hash}';

ALTER USER fraudguard_superset
IDENTIFIED WITH sha256_hash BY '${superset_hash}';

GRANT fraudguard_superset_role TO fraudguard_superset;
ALTER USER fraudguard_superset DEFAULT ROLE fraudguard_superset_role;
SQL
