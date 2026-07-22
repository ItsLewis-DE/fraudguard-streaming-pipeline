FROM apache/spark:3.5.8

USER root

ARG HADOOP_AWS_VERSION=3.3.4
ARG AWS_SDK_BUNDLE_VERSION=1.12.262
ARG SPARK_CONNECTOR_VERSION=3.5.8
ARG KAFKA_CLIENTS_VERSION=3.4.1
ARG COMMONS_POOL2_VERSION=2.11.1

ADD https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/${HADOOP_AWS_VERSION}/hadoop-aws-${HADOOP_AWS_VERSION}.jar /opt/spark/jars/hadoop-aws.jar
ADD https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/${AWS_SDK_BUNDLE_VERSION}/aws-java-sdk-bundle-${AWS_SDK_BUNDLE_VERSION}.jar /opt/spark/jars/aws-java-sdk-bundle.jar
ADD https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.12/${SPARK_CONNECTOR_VERSION}/spark-sql-kafka-0-10_2.12-${SPARK_CONNECTOR_VERSION}.jar /opt/spark/jars/spark-sql-kafka.jar
ADD https://repo1.maven.org/maven2/org/apache/spark/spark-token-provider-kafka-0-10_2.12/${SPARK_CONNECTOR_VERSION}/spark-token-provider-kafka-0-10_2.12-${SPARK_CONNECTOR_VERSION}.jar /opt/spark/jars/spark-token-provider-kafka.jar
ADD https://repo1.maven.org/maven2/org/apache/spark/spark-avro_2.12/${SPARK_CONNECTOR_VERSION}/spark-avro_2.12-${SPARK_CONNECTOR_VERSION}.jar /opt/spark/jars/spark-avro.jar
ADD https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/${KAFKA_CLIENTS_VERSION}/kafka-clients-${KAFKA_CLIENTS_VERSION}.jar /opt/spark/jars/kafka-clients.jar
ADD https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/${COMMONS_POOL2_VERSION}/commons-pool2-${COMMONS_POOL2_VERSION}.jar /opt/spark/jars/commons-pool2.jar

RUN chmod 0644 /opt/spark/jars/hadoop-aws.jar \
    /opt/spark/jars/aws-java-sdk-bundle.jar \
    /opt/spark/jars/spark-sql-kafka.jar \
    /opt/spark/jars/spark-token-provider-kafka.jar \
    /opt/spark/jars/spark-avro.jar \
    /opt/spark/jars/kafka-clients.jar \
    /opt/spark/jars/commons-pool2.jar

USER 185
