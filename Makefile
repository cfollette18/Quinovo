.PHONY: dev test install assets lint hooks evals

install:
	uv sync --all-extras

dev: install
	uv run uvicorn quinovo.api.app:create_app --factory --reload --host 127.0.0.1 --port 8791

test: install
	uv run pytest -q

lint: install
	uv run ruff check src/ tests/

assets:
	uv run --with pillow python scripts/render_demo.py

hooks:
	install -m 0755 scripts/githooks/commit-msg .git/hooks/commit-msg

evals:
	./evals/install.sh
