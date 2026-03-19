# Clinic Configuration Risk Analyzer

A tool for analyzing how proposed feature changes interact with diverse clinic configurations in multi-tenant EMR systems. Given a feature change specification, it identifies configuration conflicts, classifies risk severity, and generates a phased rollout plan.

## Quick Start

**Prerequisites:** Python 3.9+, PyYAML

```bash
pip install -r requirements.txt

# Detect conflicts for a feature change
make run FEATURE=prescribing_redesign

# Or run directly
python -m src.conflict_detector features/prescribing_redesign.yaml

# Generate rollout plan
python -m src.rollout_planner features/prescribing_redesign.yaml

# Run tests
make test
```

## How It Works

1. **Model clinic configurations** as structured YAML with province-specific constraints, enabled modules, billing types, integrations, templates, and role permissions
2. **Detect conflicts** by analyzing each proposed change against every clinic's configuration, checking for province mismatches, missing integrations, module dependencies, template breakage, role permission conflicts, and billing incompatibilities
3. **Generate rollout plans** with risk-scored cohorts, clinic-specific test cases, and stage gates between waves

## Project Structure

```
clinic-config-risk-analyzer/
  configs/
    schema.yaml                   # Configuration dimension definitions and constraints
    clinics/                      # 15 clinic configuration profiles
      edmonton_family.yaml
      calgary_specialist.yaml
      vancouver_multi.yaml
      ...
  features/                       # Feature change specifications
    prescribing_redesign.yaml
    autochart_v2.yaml
    connect_messaging_overhaul.yaml
  src/
    models.py                     # Data models and YAML loaders
    conflict_detector.py          # Conflict detection engine
    rollout_planner.py            # Rollout plan generator
  tests/
    fixtures/                     # Test data
  docs/
    edge-cases/                   # 10 edge case categories
  Makefile
  requirements.txt
```

## Available Features

Three sample feature changes are included:

- **prescribing_redesign** - PrescribeIT API upgrade, province-specific formulary validation, template field renames, nurse permission changes, billing code updates
- **autochart_v2** - New extraction categories, Scribe-AutoChart dependency, template field renames
- **connect_messaging_overhaul** - Auto-release policy change, new messaging tiers, caregiver consent workflow

## Example Output

```
$ python -m src.conflict_detector features/prescribing_redesign.yaml

Conflict Report: Prescribing Workflow Redesign
----------------------------------------------
Version: 1.0
Changes: 8

Clinics affected: 15
Total conflicts:  136 (breaking: 76, behavioral: 56, cosmetic: 4)

----------------------------------------------------------------------
| Clinic                          | Province | Breaking | Behavioral |
----------------------------------------------------------------------
| Calgary Specialist Centre       | AB       | 7        | 3          |
| Solo NP Rural Clinic            | AB       | 7        | 5          |
| Edmonton Family Medical Clinic  | AB       | 6        | 2          |
| Kelowna Walk-In Clinic          | BC       | 6        | 7          |
| Mountain View Family Practice   | AB       | 6        | 1          |
| ...                             |          |          |            |
----------------------------------------------------------------------

$ python -m src.rollout_planner features/prescribing_redesign.yaml

Prescribing Workflow Redesign -- Rollout Plan
---------------------------------------------
Total clinics: 15
Cohorts: 4

----------------------------------------------------------------------
| Clinic                          | Risk Score | Cohort               |
----------------------------------------------------------------------
| Ottawa Walk-In Centre           | 51.0       | Cohort 1: Low Risk   |
| Red Deer Solo Practice          | 59.5       | Cohort 1: Low Risk   |
| Pacific Walk-In Clinic          | 61.5       | Cohort 1: Low Risk   |
| Toronto Family Health Centre    | 62.5       | Cohort 1: Low Risk   |
| ...                             |            |                      |
| Calgary Specialist Centre       | 105.5      | Cohort 4: Critical   |
----------------------------------------------------------------------

Cohort 1: Low Risk
  Gate: Zero critical bugs for 48 hours
  Test Cases:
    1. Smoke test for Ottawa Walk-In Centre
       Verify core workflows at Ottawa Walk-In Centre (ON, walk_in).
    2. Breaking change validation - Ottawa Walk-In Centre
       Validate breaking change in 'integrations': Clinic uses
       province-specific integration 'prescribeit' which is modified.
```

## Adding Clinic Profiles

Create a YAML file in `configs/clinics/` following the schema in `configs/schema.yaml`. Each profile defines a clinic's province, type, modules, integrations, billing types, templates, role permissions, and scheduling configuration. See existing profiles for examples.

## Adding Feature Changes

Create a YAML file in `features/` with the change specification format. Each change entry specifies the affected dimension, change type, province scope, module and integration requirements, template impacts, and permission modifications. See existing features for the structure.

## HTML Report

Generate an interactive HTML report for stakeholder review:

```bash
make report FEATURE=prescribing_redesign
# Opens report.html with summary stats, province filter, risk sorting,
# and expandable clinic details
```

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Quality checks
make lint          # ruff check + format
make typecheck     # mypy strict mode
make coverage      # pytest with 90% coverage threshold
make qa            # lint + typecheck + coverage (all three)

# E2E tests (Playwright)
python -m playwright install chromium
make e2e
```

See [TESTING.md](TESTING.md) for the full testing strategy and CI pipeline documentation.

## Design Decisions

See [DECISIONS.md](DECISIONS.md) for assumptions, tradeoffs, and areas of uncertainty.

## Edge Cases

The `docs/edge-cases/` directory catalogs 10 categories of edge cases relevant to multi-tenant EMR feature rollouts, including cross-province scenarios, integration failures, template divergence, scheduling conflicts, and audit trail considerations.
