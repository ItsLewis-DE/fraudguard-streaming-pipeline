FROM apache/airflow:3.2.2-python3.12

USER airflow

COPY docker/airflow/requirements.txt /tmp/requirements.txt

# Pin Airflow to the base-image version so installing the ClickHouse client
# cannot implicitly upgrade or downgrade Airflow.
RUN pip install --no-cache-dir \
    "apache-airflow==3.2.2" \
    -r /tmp/requirements.txt
