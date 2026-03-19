# Testing Strategy

This project uses a three-tier test strategy designed for reliability in a healthcare configuration management context.

## Test Tiers

### Tier 1: Unit Tests (`tests/test_conflict_detector.py`, `tests/test_rollout_planner.py`)

Test individual detection checks and scoring functions in isolation using fixture clinics and synthetic changes.

**What they cover:**
- Province mismatch detection across all 3 provinces
- YAML boolean province parsing (ON/NO parsed as True/False by PyYAML)
- Module dependency checks
- Template breakage detection
- Missing integration detection with guard logic
- Billing change severity mapping (remove/modify = breaking, add = cosmetic)
- Risk score formula with known inputs
- Cohort ordering invariants
- Malformed/minimal config handling

**Why they matter for healthcare:** Each unit test targets a specific failure mode. The YAML boolean test catches a real parsing bug where Ontario clinics fail to load. The billing severity tests ensure destructive changes always surface as breaking conflicts.

### Tier 2: Integration Tests (`tests/test_integration.py`)

Run the full pipeline (load all 15 clinics, detect conflicts, generate plans, produce reports) for every feature specification.

**What they cover:**
- End-to-end conflict detection for all 3 features x 15 clinics
- Rollout plan generation with structural validation
- Terminal report output (conflict + rollout reports)
- HTML report generation with content verification

**Why they matter for healthcare:** With 300+ clinics in production, you cannot manually verify every configuration interaction. Parametrized integration tests scale verification to match the problem space.

### Tier 3: E2E Tests (`tests/e2e/`)

Use Playwright to test the interactive HTML report in a real browser.

**What they cover:**
- Report content: title, stat cards, 15 clinic cards with valid data attributes
- Province filter: selecting BC shows only BC clinics, selecting All restores 15
- Sort buttons: risk descending/ascending, alphabetical name sort
- Expand/collapse: clicking clinic headers shows/hides conflict details
- Visual regression: captures screenshots for baseline comparison

**Why they matter for healthcare:** If stakeholders cannot read and interact with the report, the analysis data is inaccessible. E2E tests ensure the report works as intended for non-technical users reviewing rollout risk.

## Running Tests

```bash
# All unit + integration tests
make test

# With coverage enforcement (90% minimum)
make coverage

# E2E tests (requires Playwright)
python -m playwright install chromium
make e2e

# Full quality check (lint + typecheck + test)
make qa
```

## Coverage

Target: 90% line coverage on `src/`.

The `__main__` blocks are excluded from coverage (CLI entry points). Current coverage sits around 96%.

## CI Pipeline

The CI runs 5 jobs:

1. **lint** - ruff check + format verification
2. **typecheck** - mypy strict mode
3. **test** - pytest with 90% coverage threshold
4. **yaml-validation** - yamllint on all config files
5. **e2e** - Playwright browser tests (depends on test passing)
