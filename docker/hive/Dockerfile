FROM apache/hive:3.1.3

USER root

ARG POSTGRES_JDBC_VERSION=42.7.5
ARG HADOOP_AWS_VERSION=3.1.0
ARG AWS_SDK_BUNDLE_VERSION=1.11.271

ADD https://repo1.maven.org/maven2/org/postgresql/postgresql/${POSTGRES_JDBC_VERSION}/postgresql-${POSTGRES_JDBC_VERSION}.jar /opt/hive/lib/postgresql.jar
ADD https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/${HADOOP_AWS_VERSION}/hadoop-aws-${HADOOP_AWS_VERSION}.jar /opt/hive/lib/hadoop-aws.jar
ADD https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/${AWS_SDK_BUNDLE_VERSION}/aws-java-sdk-bundle-${AWS_SDK_BUNDLE_VERSION}.jar /opt/hive/lib/aws-java-sdk-bundle.jar
COPY docker/hive/entrypoint.sh /entrypoint-safe.sh

# Hive 3.1.3 ships PostgreSQL JDBC 9.4.1208. Keeping both drivers on the
# classpath lets the old one win, and it cannot authenticate to PostgreSQL 16
# using SCRAM-SHA-256 (authentication type 10).
RUN rm -f /opt/hive/lib/postgresql-9.4.1208.jre7.jar \
    && chmod 0644 /opt/hive/lib/postgresql.jar \
    /opt/hive/lib/hadoop-aws.jar \
    /opt/hive/lib/aws-java-sdk-bundle.jar \
    && chmod 0755 /entrypoint-safe.sh

USER hive

ENTRYPOINT ["/entrypoint-safe.sh"]
