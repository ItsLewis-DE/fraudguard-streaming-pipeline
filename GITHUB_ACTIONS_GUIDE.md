# Hướng dẫn thêm GitHub Actions cho FraudGuard

Tài liệu này hướng dẫn tạo CI phù hợp với trạng thái hiện tại của FraudGuard:
Python 3.12, `uv`, Ruff, mypy, pytest, dbt, Docker Compose và Airflow.
Mục tiêu đầu tiên là kiểm tra nhanh, tái lập được trên mỗi pull request; không
khởi động toàn bộ Kafka/Spark/MinIO/ClickHouse/Airflow trong CI mặc định.

## 1. Hiện trạng đã kiểm tra

Tại thời điểm viết tài liệu:

| Kiểm tra | Kết quả | Ý nghĩa |
|---|---|---|
| `uv run ruff check ...` | Pass | Có thể bật ngay trong CI |
| `uv run pytest -m smoke --no-cov` | 16 test pass | Có thể bật ngay trong CI |
| `uv run dbt parse ...` | Pass | Có thể kiểm tra cú pháp/manifest dbt mà không cần ClickHouse |
| `docker compose config --quiet` | Pass | Có thể kiểm tra cấu hình Compose bằng mật khẩu giả |
| `uv run ruff format --check ...` | Fail ở 9 file | Chưa nên đặt làm required check trước khi format code |
| `uv run mypy ...` | Fail 22 lỗi | Cần xử lý type stubs trước khi bật làm required check |

Ngoài ra, `pyproject.toml` khai báo `readme = "README.md"` nhưng repository chưa
có `README.md` ở thư mục gốc. Nên bổ sung file này trước khi coi việc cài package
trên máy sạch là ổn định.

## 2. Thiết kế CI phù hợp

Nên chia thành hai tầng:

1. **CI nhanh trên pull request:** lint, smoke tests, `dbt parse` và
   `docker compose config`. Không cần service, dataset hoặc secret thật.
2. **Integration workflow riêng:** chỉ chạy thủ công hoặc theo lịch sau này,
   khi đã có test thực sự cần Kafka, MinIO, ClickHouse, Spark và Airflow.

Không nên chạy toàn bộ stack ở mỗi commit vì Docker Compose hiện có nhiều
service nặng. Việc này làm CI chậm, tốn tài nguyên và khó xác định nguyên nhân
khi một healthcheck hạ tầng bị lỗi.

Chỉ kiểm tra Python 3.12 ở giai đoạn hiện tại vì:

- image Airflow đang dùng Python 3.12;
- `pyproject.toml` yêu cầu Python từ 3.12;
- dự án chưa có mục tiêu hỗ trợ nhiều phiên bản Python.

## 3. Chuẩn bị trước khi tạo workflow

### 3.1 Đồng bộ môi trường

Chạy tại thư mục gốc:

```bash
uv sync --locked --dev
```

`--locked` làm CI thất bại nếu `pyproject.toml` và `uv.lock` không đồng bộ.
Không dùng `uv sync` không khóa trong CI vì nó có thể âm thầm chọn dependency
khác với máy local.

### 3.2 Chạy các gate đang pass

```bash
uv run ruff check airflow/dags ml/src/fraudguard_ml ml/tests producer spark/jobs
uv run pytest -m smoke --no-cov
```

Kiểm tra dbt bằng thư mục output tạm:

```bash
uv run dbt parse \
  --project-dir dbt \
  --profiles-dir dbt \
  --target dev \
  --target-path /tmp/fraudguard-dbt-ci-target \
  --log-path /tmp/fraudguard-dbt-ci-logs \
  --no-partial-parse
```

`dbt parse` chỉ kiểm tra khả năng parse project. Nó không thay thế
`dbt build` và các data tests chạy với ClickHouse.

### 3.3 Xử lý các gate đang fail

Kiểm tra rồi format code:

```bash
uv run ruff format --check airflow/dags ml/src/fraudguard_ml ml/tests producer spark/jobs
uv run ruff format airflow/dags ml/src/fraudguard_ml ml/tests producer spark/jobs
```

Sau khi format, review diff trước khi commit.

Kiểm tra mypy:

```bash
uv run mypy ml/src/fraudguard_ml ml/tests
```

Các lỗi hiện tại chủ yếu đến từ package không cung cấp type information như
`boto3`, `pandas`, `pyarrow`, `joblib`, `scikit-learn` và `scipy`. Cách xử lý:

1. Thêm stub package có chất lượng vào dependency group `dev` khi có.
2. Với package không có stub đáng tin cậy, thêm override **theo từng module**
   trong cấu hình mypy.
3. Không bật `ignore_missing_imports = true` toàn cục vì sẽ che lỗi type thật
   trong toàn bộ dự án.

Đây là thay đổi dependency/config riêng, cần được review và cập nhật
`uv.lock` trước khi bật mypy thành required check.

## 4. Tạo workflow CI giai đoạn 1

Tạo thư mục và file:

```text
.github/
└── workflows/
    └── ci.yml
```

Dùng nội dung sau:

```yaml
name: CI

on:
  pull_request:
  push:
    branches:
      - main
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  quality:
    name: Python and dbt checks
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - name: Check out repository
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - name: Set up Python
        uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: "3.12"

      - name: Install uv
        uses: astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9 # v9.0.0
        with:
          enable-cache: true

      - name: Install locked dependencies
        run: uv sync --locked --dev

      - name: Lint Python
        run: >-
          uv run ruff check
          airflow/dags
          ml/src/fraudguard_ml
          ml/tests
          producer
          spark/jobs

      - name: Run smoke tests
        run: uv run pytest -m smoke --no-cov

      - name: Parse dbt project
        run: >-
          uv run dbt parse
          --project-dir dbt
          --profiles-dir dbt
          --target dev
          --target-path "$RUNNER_TEMP/dbt-target"
          --log-path "$RUNNER_TEMP/dbt-logs"
          --no-partial-parse

  compose-config:
    name: Validate Docker Compose
    runs-on: ubuntu-latest
    timeout-minutes: 5
    env:
      CLICKHOUSE_LOADER_PASSWORD: ci-not-a-real-secret
      DBT_CLICKHOUSE_PASSWORD: ci-not-a-real-secret
      CLICKHOUSE_SUPERSET_PASSWORD: ci-not-a-real-secret
      CLICKHOUSE_ML_PASSWORD: ci-not-a-real-secret

    steps:
      - name: Check out repository
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - name: Validate Compose rendering
        run: docker compose config --quiet
```

### Vì sao workflow này phù hợp

- `contents: read` áp dụng nguyên tắc quyền tối thiểu.
- `persist-credentials: false` tránh giữ Git credential sau bước checkout.
- `concurrency` hủy CI của commit cũ khi có commit mới trên cùng branch.
- Action được pin bằng commit SHA để giảm supply-chain risk; comment vẫn cho
  biết phiên bản dễ đọc.
- `uv sync --locked --dev` sử dụng đúng `uv.lock` và dependency group hiện tại.
- CI dùng lệnh kiểm tra, không dùng `ruff check --fix` nên không tự sửa code.
- Mật khẩu trong job Compose chỉ là placeholder để kiểm tra interpolation.
  Job không khởi động container và không kết nối dịch vụ.
- Workflow không cần repository secrets ở giai đoạn 1.

Các SHA trong mẫu được đối chiếu ngày 2026-08-19. Khi cập nhật action, kiểm tra
release chính thức rồi cập nhật cả SHA và comment phiên bản.

## 5. Nâng cấp quality gate ở giai đoạn 2

Sau khi format code và xử lý mypy, thêm các step sau vào job `quality`, sau
bước lint:

```yaml
      - name: Check Python formatting
        run: >-
          uv run ruff format --check
          airflow/dags
          ml/src/fraudguard_ml
          ml/tests
          producer
          spark/jobs

      - name: Type check ML package
        run: uv run mypy ml/src/fraudguard_ml ml/tests
```

Sau khi test coverage thực sự đạt ngưỡng 80% đã khai báo trong
`pyproject.toml`, thay smoke test bằng:

```yaml
      - name: Run service-free tests with coverage
        run: uv run pytest -m "not integration and not gpu"
```

Không giảm `--cov-fail-under=80` chỉ để CI xanh. Nếu coverage chưa đủ, giữ
smoke test làm required check và bổ sung unit tests trước.

## 6. Quan hệ với pre-commit hiện tại

`.pre-commit-config.yaml` hiện chạy:

- `ruff check --fix`;
- `ruff format --check`;
- mypy;
- smoke tests.

Khác biệt đúng giữa local và CI:

| Local pre-commit | GitHub Actions |
|---|---|
| Có thể dùng `--fix` để hỗ trợ developer | Chỉ kiểm tra, không sửa commit |
| Phản hồi trước khi commit | Xác minh lại trên máy sạch |
| Có thể bị bỏ qua bằng `--no-verify` | Là required check trên pull request |

Khi mypy và format đã sạch, bảo đảm câu lệnh ở pre-commit và CI dùng cùng phạm
vi file để tránh tình trạng local pass nhưng CI fail.

## 7. Không đưa full stack vào PR CI ngay

Luồng thực tế gồm:

```text
Kafka → Spark → MinIO → Airflow → ClickHouse → dbt
      → snapshot → diagnostics → train → evaluate
```

Luồng này cần nhiều container, healthcheck, dữ liệu đầu vào và thời gian chờ.
Nên tạo `.github/workflows/integration.yml` riêng khi đã có acceptance test rõ
ràng. Trigger ban đầu nên là:

```yaml
name: Integration

on:
  workflow_dispatch:
  schedule:
    - cron: "0 3 * * 1"

permissions:
  contents: read
```

Integration workflow tương lai nên thực hiện theo thứ tự:

1. Render và build Docker Compose.
2. Khởi động đúng nhóm service cần thiết, không mặc định khởi động tất cả.
3. Chờ healthcheck thay vì dùng `sleep` cố định.
4. Nạp một fixture nhỏ, deterministic.
5. Chạy ingestion/dbt/training acceptance test.
6. Thu thập log khi thất bại bằng `if: failure()`.
7. Luôn chạy `docker compose down -v` bằng `if: always()`.

Không dùng dataset PaySim đầy đủ trong CI và không commit credential thật.

## 8. Push và quan sát workflow

Sau khi tự tạo `.github/workflows/ci.yml`:

```bash
git add .github/workflows/ci.yml
git diff --cached
git commit -m "ci: add fast validation workflow"
git push
```

Trên GitHub:

1. Mở tab **Actions**.
2. Chọn workflow **CI**.
3. Mở từng job `Python and dbt checks` và `Validate Docker Compose`.
4. Nếu workflow không xuất hiện, kiểm tra file đã nằm đúng
   `.github/workflows/*.yml` và YAML đã được push.

## 9. Bật branch protection sau khi CI xanh

Chỉ cấu hình required checks sau khi workflow đã chạy xanh ít nhất một lần:

1. Vào **Settings → Rules → Rulesets** hoặc phần bảo vệ branch.
2. Áp dụng cho branch `main`.
3. Yêu cầu pull request trước khi merge.
4. Yêu cầu hai status check:
   - `Python and dbt checks`;
   - `Validate Docker Compose`.
5. Yêu cầu branch cập nhật với `main` trước khi merge nếu repository thường có
   nhiều pull request song song.

Không bật mypy/format/full coverage thành required check trước khi các lỗi hiện
tại được xử lý; nếu không, mọi pull request sẽ bị khóa bởi technical debt cũ.

## 10. Xử lý lỗi thường gặp

### `uv sync --locked` thất bại

- Kiểm tra `pyproject.toml` và `uv.lock` có đồng bộ không.
- Chạy `uv lock --check` tại local.
- Nếu dependency chủ đích thay đổi, chạy `uv lock` rồi review diff.
- Kiểm tra `README.md` gốc vì `pyproject.toml` đang tham chiếu file này.

### Ruff format thất bại

```bash
uv run ruff format airflow/dags ml/src/fraudguard_ml ml/tests producer spark/jobs
git diff
```

### mypy báo `import-untyped`

Không tắt strict mode toàn cục. Thêm stub hoặc override hẹp theo package, rồi
chạy lại đúng lệnh mypy của CI.

### pytest thất bại vì coverage

Phân biệt:

- `pytest -m smoke --no-cov`: kiểm tra nhanh, không áp coverage gate;
- `pytest -m "not integration and not gpu"`: áp cấu hình coverage trong
  `pyproject.toml`.

Tăng test cho code chưa được bao phủ thay vì hạ ngưỡng chỉ để merge.

### dbt parse có warning về `seeds.fraudguard`

Warning hiện tại cho biết cấu hình seed chưa áp dụng cho resource nào. Nó không
làm `dbt parse` thất bại, nhưng nên dọn khi quyết định dự án không dùng seed.

### Compose validation yêu cầu password

Chỉ job `docker compose config` mới dùng placeholder. Khi chạy integration thật,
dùng GitHub repository secrets và không in secret ra log.

## 11. Tiêu chí hoàn thành

Giai đoạn 1 hoàn thành khi:

- pull request và push vào `main` tự chạy CI;
- lint, smoke tests, `dbt parse` và Compose validation đều xanh;
- workflow không dùng secret thật;
- branch protection chặn merge khi hai job thất bại;
- developer chạy được các lệnh tương đương tại local.

Giai đoạn 2 hoàn thành khi:

- toàn bộ code đã qua `ruff format --check`;
- mypy strict pass sau khi xử lý type stubs;
- service-free test coverage đạt tối thiểu 80%;
- integration workflow có fixture nhỏ và teardown đáng tin cậy.

## Tài liệu chính thức

- [GitHub Actions: build và test Python](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)
- [GitHub Actions: concurrency](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency)
- [uv trong GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/)
- [actions/checkout](https://github.com/actions/checkout)
