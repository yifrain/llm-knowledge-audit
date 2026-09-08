.PHONY: install check demo pilot-plan
install:
	uv sync --frozen --extra dev --extra plots
check:
	uv run --frozen --extra dev pytest
	uv run --frozen --extra dev ruff check .
	uv run --frozen --extra dev --extra plots mypy src
demo:
	uv run --frozen llmka run-all --config configs/mock.yaml
pilot-plan:
	uv run --frozen llmka pilot-plan --config configs/pilot.yaml
