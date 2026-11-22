# Use uv and pyproject.toml for dependency management

* Status: accepted
* Deciders: Imran Qureshi
* Date: 2026-11-21
* Jira: BAI-1957

## Context and Problem Statement

compressed-fhir managed dependencies with Pipenv (`Pipfile`, `Pipfile.lock`) and kept package metadata in a separate `setup.py`, with `pipenv-setup` syncing the two. Dependencies were declared twice, the sync tool conflicted with the dev dependencies, and the lock was slow to regenerate. Other b.well Python repositories (for example `helix.fhir.client.sdk`) have already moved to uv.

## Considered Options

* Keep Pipenv and `setup.py`
* Poetry
* uv with a PEP 621 `pyproject.toml`

## Decision Outcome

Chosen option: **uv with `pyproject.toml`**, because it keeps a single source of truth for dependencies (`[project] dependencies` and `[dependency-groups] dev`), produces a cross-platform `uv.lock`, matches the tooling the other b.well Python repositories use, and removes the need for `pipenv-setup` and `setup.py`.

### Consequences

* `Pipfile`, `Pipfile.lock`, `setup.py` and `setup.cfg` are removed; tool configuration (pytest, mypy, ruff) lives in `pyproject.toml`.
* The package is built with `uv build` using the setuptools backend, with the version read from `VERSION`.
* The wheel now includes only `compressedfhir*` packages; the previous `find_packages()` also picked up the top-level `tests` package.
* The uv image is pinned by digest in `Dockerfile` and `pre-commit.Dockerfile`; both must be bumped together.
* The repository has only public dependencies, so no JFrog index is configured.
