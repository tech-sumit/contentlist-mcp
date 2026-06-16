FROM python:3.12-slim

# Trafilatura/lxml need a couple of build/runtime libs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV MCP_TRANSPORT=streamable-http HOST=0.0.0.0 PORT=8000
EXPOSE 8000
CMD ["contentlist-mcp"]
