.PHONY: setup test lint

# Install deps and work around the recurring macOS/APFS issue where the editable
# install's .pth files get marked hidden, causing `ModuleNotFoundError: multibatch`.
setup:
	uv sync
	chflags -R nohidden .venv 2>/dev/null || true

test:
	uv run --no-sync pytest

lint:
	uv run --no-sync ruff check src
