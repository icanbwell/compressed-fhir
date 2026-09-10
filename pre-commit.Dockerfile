FROM public.ecr.aws/docker/library/python:3.12-alpine3.20

# Install git, build-essential, and pipenv
RUN apk add --no-cache git build-base && \
    pip install pipenv

# Copy Pipfile and Pipfile.lock
COPY Pipfile* ./

# Install dependencies using pipenv
RUN pipenv sync --dev --system

# Create non-root user
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Set the working directory
WORKDIR /sourcecode

# Use system-level git config so it's accessible by non-root user
RUN git config --system --add safe.directory /sourcecode

USER appuser

CMD ["pre-commit", "run", "--all-files"]
