.PHONY: setup test lint

# The venv lives in .venv.nosync so iCloud (Desktop & Documents sync) never
# evicts its files; .venv is a symlink kept for tooling. Plain `uv sync` and
# `uv run` work through the symlink once it exists.
setup:
	UV_PROJECT_ENVIRONMENT=.venv.nosync uv sync
	@if [ ! -L .venv ]; then rm -rf .venv && ln -s .venv.nosync .venv; fi

test:
	uv run --no-sync pytest

lint:
	uv run --no-sync ruff check src
