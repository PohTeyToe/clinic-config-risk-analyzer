.PHONY: test run rollout clean

FEATURE ?= prescribing_redesign

test:
	python -m pytest tests/ -v

run:
	python -m src.conflict_detector features/$(FEATURE).yaml

rollout:
	python -m src.rollout_planner features/$(FEATURE).yaml

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type f -name "*.pyc" -delete 2>/dev/null; true
