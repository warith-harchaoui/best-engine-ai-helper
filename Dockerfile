# syntax=docker/dockerfile:1.6
#
# best-engine-ai-helper — reproducible container image.
#
# The container runs the CLI only (detect, recommend, catalog show, hardware show).
# It does NOT include Ollama. Ollama runs on the host; the container reaches it
# through SPREZZATURE_LLM_BASE_URL (default http://host.docker.internal:11434 on
# Docker Desktop, or set via --env on Linux).
#
# Build:
#   docker build -t best-engine-ai-helper .
#
# Run (print hardware detected inside the container):
#   docker run --rm best-engine-ai-helper detect
#
# Run (recommend models for this hardware):
#   docker run --rm best-engine-ai-helper recommend
#
# Run (pull via Ollama on the host, Linux):
#   docker run --rm \
#     --env SPREZZATURE_LLM_BASE_URL=http://172.17.0.1:11434 \
#     best-engine-ai-helper pull

# --- base -------------------------------------------------------------------
FROM python:3.11-slim AS base

# curl is used by the validate commands to health-check the Ollama endpoint
# before running inference calls. No compilers; we install from wheels only.
RUN apt-get update && apt-get install --no-install-recommends -y \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only the package files needed for installation; this layer is cached
# independently from the source code so repeated builds are fast.
WORKDIR /app
COPY pyproject.toml requirements.txt ./
COPY best_engine_ai_helper/ ./best_engine_ai_helper/
COPY models.yaml hardware.yaml ./

# Install the package and its runtime dependencies from wheels.
# The [dev] extra is intentionally excluded so the image stays small.
RUN pip install --no-cache-dir -e .

# --- final ------------------------------------------------------------------
FROM base AS final

# Set a non-root user for safety; Ollama on the host handles its own auth.
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

# Default command: recommend models for the detected hardware.
# Override with any other subcommand (detect, catalog show, etc.).
CMD ["best-engine-ai-helper", "recommend"]
