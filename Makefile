.PHONY: setup test lint

# The venv lives in .venv.nosync so iCloud (Desktop & Documents sync) never
# evicts its files; .venv is a symlink kept for tooling. Plain `uv sync` and
# `uv run` work through the symlink once it exists. The chflags step clears
# the UF_HIDDEN flag uv/iCloud set on .pth files, which Python 3.13+ would
# otherwise skip (symptom: ModuleNotFoundError: No module named 'multibatch').
setup:
	UV_PROJECT_ENVIRONMENT=.venv.nosync uv sync
	@if [ ! -L .venv ]; then rm -rf .venv && ln -s .venv.nosync .venv; fi
	@chflags -R nohidden .venv.nosync

test:
	uv run --no-sync pytest

lint:
	uv run --no-sync ruff check src
