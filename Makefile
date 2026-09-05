.PHONY: install install-detect test lint format demo corpus scenarios clean

# --- Setup ---
install:
	uv pip install --python .venv/bin/python -e ".[dev]"

install-detect:
	uv pip install --python .venv/bin/python -e ".[detect]"
	.venv/bin/python -m spacy download en_core_web_lg

# --- Quality ---
test:
	python3 -m pytest -q

lint:
	ruff check src tests

format:
	ruff format src tests

# --- Corpus (build step 1) ---
corpus:
	python3 -m socareguard.corpus generate
	python3 -m socareguard.corpus inject
	python3 -m socareguard.corpus stats

scenarios:
	python3 -m socareguard.scenarios build
	python3 -m socareguard.scenarios validate

# --- Demo ---
DEMO_CMD ?= python3 -m socareguard.proxy

demo:
	$(DEMO_CMD)

# --- Cleanup (build intermediates only; never touches corpus/ or demo/) ---
clean:
	find . -type d -name __pycache__ -prune -exec rm -r {} +
	rm -r .pytest_cache .ruff_cache build dist *.egg-info 2>/dev/null || true
