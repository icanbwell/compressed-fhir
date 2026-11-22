# Stage 1: Base image to install common dependencies and lock Python dependencies
# This stage is responsible for setting up the environment and installing Python packages using uv.
FROM public.ecr.aws/docker/library/python:3.12-alpine3.20 AS python_packages

# Set terminal width (COLUMNS) and height (LINES)
ENV COLUMNS=300

# Define an argument to control whether to run uv lock (used for updating uv.lock)
ARG RUN_UV_LOCK=false

# Install common tools and dependencies (git is required for some Python packages)
RUN apk add --no-cache git

# Install uv, a tool for managing Python project dependencies
COPY --from=ghcr.io/astral-sh/uv:0.11.6@sha256:b1e699368d24c57cda93c338a57a8c5a119009ba809305cc8e86986d4a006754 /uv /uvx /usr/local/bin/
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Set the working directory inside the container
WORKDIR /usr/src/compressedfhir/

# Copy pyproject.toml and uv.lock to the working directory
# pyproject.toml defines the Python packages required for the project
# uv.lock ensures consistency by locking the exact versions of packages
# README.md and VERSION are read by the build backend when uv resolves the project's dynamic metadata
COPY pyproject.toml uv.lock* README.md VERSION /usr/src/compressedfhir/

# Conditionally run uv lock to update uv.lock based on the argument provided
RUN if [ "$RUN_UV_LOCK" = "true" ]; then echo "Locking dependencies" && rm -f uv.lock && uv lock --verbose; fi

# Install production dependencies using the locked versions in uv.lock
RUN uv sync --frozen --no-install-project --verbose
RUN cp -f uv.lock /tmp/uv.lock

# Stage 1b: development dependencies (extends production)
FROM python_packages AS python_packages_dev
RUN uv sync --frozen --group dev --no-install-project --verbose

# Stage 2: Runtime image for the application
# This stage creates a minimal image with only the runtime dependencies and the application code.
FROM public.ecr.aws/docker/library/python:3.12-alpine3.20 AS production

# Set terminal width (COLUMNS) and height (LINES)
ENV COLUMNS=300

# Install common tools and dependencies (git is required for some Python packages)
RUN apk add --no-cache git

# uv is needed at runtime for `uv build`
COPY --from=ghcr.io/astral-sh/uv:0.11.6@sha256:b1e699368d24c57cda93c338a57a8c5a119009ba809305cc8e86986d4a006754 /uv /uvx /usr/local/bin/

# Set environment variables for project configuration
ENV PROJECT_DIR=/usr/src/compressedfhir
ENV FLASK_APP=compressedfhir.api
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create the directory for Prometheus metrics
RUN mkdir -p ${PROMETHEUS_MULTIPROC_DIR}

# Set the working directory for the project
WORKDIR ${PROJECT_DIR}

# Copy the project files into the runtime image
COPY pyproject.toml uv.lock* ${PROJECT_DIR}/

# Copy installed Python packages from the previous stage
COPY --from=python_packages /opt/venv /opt/venv

# Copy the application code into the runtime image
COPY ./compressedfhir ${PROJECT_DIR}

# Copy uv.lock from the previous stage in case it was locked
COPY --from=python_packages /tmp/uv.lock /tmp/uv.lock

# Expose port 5000 for the application
EXPOSE 5000

# Switch to the root user to perform user management tasks
USER root

# Create a restricted user (appuser) and group (appgroup) for running the application
RUN addgroup -S appgroup && adduser -S -h /etc/appuser appuser -G appgroup

# Ensure that the appuser owns the application files and directories
RUN chown -R appuser:appgroup ${PROJECT_DIR} /opt/venv ${PROMETHEUS_MULTIPROC_DIR}

# Switch to the restricted user to enhance security
USER appuser

# Stage 3: development runtime (extends production with dev dependencies)
# Tests are provided by the docker-compose volume mount of the source tree.
FROM production AS development
USER root
COPY --from=python_packages_dev /opt/venv /opt/venv
RUN chown -R appuser:appgroup /opt/venv
USER appuser

# Default: bare `docker build .` produces production image
FROM production
