.PHONY: dev test install

install:
	uv sync --all-extras

dev: install
	uv run uvicorn quinovo.api.app:create_app --factory --reload --host 127.0.0.1 --port 8791

test: install
	uv run pytest -q
