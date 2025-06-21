# Stage 1: Build dependencies and project with uv
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS uv

WORKDIR /app

# Enable bytecode compilation and copy mode for cache compatibility
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy lock and project files
COPY uv.lock pyproject.toml ./

RUN uv sync --no-dev

# Set up environment
ENV PATH="/app/.venv/bin:$PATH"

# Copy your application code
COPY main.py .


EXPOSE 8000
# Start the application
CMD ["uv", "run", "main.py"]
