.PHONY: test run rollout clean lint typecheck format coverage qa report e2e

FEATURE ?= prescribing_redesign

test:
	python -m pytest tests/ -v -m "not e2e"

coverage:
	python -m pytest tests/ -v -m "not e2e" --cov=src --cov-report=term-missing --cov-fail-under=90

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

typecheck:
	mypy src/

format:
	ruff format src/ tests/
	ruff check src/ tests/ --fix

qa: lint typecheck coverage

run:
	python -m src.conflict_detector features/$(FEATURE).yaml

rollout:
	python -m src.rollout_planner features/$(FEATURE).yaml

report:
	python -m src.html_report features/$(FEATURE).yaml report.html

e2e:
	python -m pytest tests/e2e/ -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type f -name "*.pyc" -delete 2>/dev/null; true
	rm -rf test-results/ htmlcov/ .ruff_cache/ .pytest_cache/
