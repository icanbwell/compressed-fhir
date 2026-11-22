FROM public.ecr.aws/docker/library/python:3.12-alpine3.20

# Install git and build-base
RUN apk add --no-cache git build-base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.11.6@sha256:b1e699368d24c57cda93c338a57a8c5a119009ba809305cc8e86986d4a006754 /uv /uvx /usr/local/bin/
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PATH="/opt/venv/bin:$PATH"

# Copy pyproject.toml, uv.lock and the files read for its dynamic metadata
COPY pyproject.toml uv.lock* README.md VERSION ./

# Install production and dev dependencies (linters need both to type-check tests)
RUN uv sync --frozen --group dev --no-install-project

# Create non-root user
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Set the working directory
WORKDIR /sourcecode

# Use system-level git config so it's accessible by non-root user
RUN git config --system --add safe.directory /sourcecode

USER appuser

CMD ["pre-commit", "run", "--all-files"]
