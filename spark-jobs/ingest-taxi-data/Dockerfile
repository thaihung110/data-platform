# Dockerfile for Spark jobs with Python code
# Use official Apache Spark image with Python support
FROM apache/spark:3.5.0-python3

# Switch to root for any setup needed
USER root

# Set working directory
WORKDIR /app

# Copy Python application code
COPY ingest_taxi_data.py /app/ingest_taxi_data.py

# Make script executable and set ownership/permissions
RUN chmod +x /app/ingest_taxi_data.py && \
    chmod 777 /app && \
    chown -R 185:185 /app

# Switch back to default spark user (uid 185)
USER 185

