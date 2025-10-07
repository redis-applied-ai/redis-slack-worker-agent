FROM python:3.12.10-slim

# Install system dependencies including curl for health checks and git
RUN apt-get update && apt-get install -y curl git && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files first (for better layer caching)
COPY pyproject.toml ./
COPY uv.lock ./
COPY README.md ./

# Create virtual environment and install dependencies from lockfile
RUN uv sync

# Copy the rest of the application
COPY . .

# Set the Python path to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Ensure the startup script has proper permissions and line endings
RUN chmod +x start.sh && \
    sed -i 's/\r$//' start.sh

# Expose port
EXPOSE 3000

# Run both app and worker
CMD ["./start.sh"]
