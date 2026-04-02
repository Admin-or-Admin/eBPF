# Use a lightweight Python image
FROM python:3.11-slim

# Install system dependencies (curl for fetching tetra, tar for extraction)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    tar \
    && rm -rf /var/lib/apt/lists/*

# Install Tetragon's tetra CLI
RUN curl -L https://github.com/cilium/tetragon/releases/download/v0.11.0/tetra-linux-amd64.tar.gz | tar -xz -C /usr/local/bin/

# Set working directory
WORKDIR /app

# Copy shared library first
COPY shared/ /app/shared/
RUN cd /app/shared && pip install .

# Copy ebpf source
COPY ebpf/ /app/ebpf/

# Set PYTHONPATH to include the root for consistent imports
ENV PYTHONPATH=/app

# Command to run the reader
# Note: Use -u for unbuffered output to see logs in docker logs
CMD ["python", "-u", "ebpf/reader.py"]
