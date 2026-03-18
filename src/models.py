"""Data models and YAML loaders for the Clinic Configuration Risk Analyzer."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import yaml

# PyYAML (YAML 1.1) treats ON/NO/YES/OFF as booleans.  Province codes
# like "ON" (Ontario) and "NO" (hypothetical) get parsed as True/False.
# This mapping converts them back.
_YAML_BOOL_TO_PROVINCE = {
    True: "ON",
    False: "NO",
}


def _fix_yaml_province(value: object) -> str:
    """Convert a YAML-parsed province value to a string.

    Handles the YAML 1.1 quirk where ON -> True and NO -> False.
    """
    if isinstance(value, bool):
        return _YAML_BOOL_TO_PROVINCE.get(value, str(value))
    return str(value)


@dataclass
class ClinicConfig:
    """Represents a single clinic's configuration loaded from YAML."""

    name: str
    province: str
    clinic_type: str
    provider_count: int
    providers: list[str]
    modules: list[str]
    connect_settings: dict[str, Any] | None
    scribe_settings: dict[str, Any] | None
    autochart_settings: dict[str, Any] | None
    billing: list[str]
    integrations: list[str]
    scheduling: dict[str, Any]
    role_permissions: dict[str, list[str]]
    templates: dict[str, list[str]]
    panelling: dict[str, Any] | None
    file_name: str


@dataclass
class Change:
    """A single change within a feature release."""

    dimension: str
    field: str | None
    change_type: str  # add / modify / remove / rename
    description: str
    old_value: Any | None
    new_value: Any | None
    affects_provinces: list[str]  # province codes or ["all"]
    requires_modules: list[str]
    requires_integrations: list[str]
    breaks_templates: list[str]
    permission_changes: dict[str, str] | None


@dataclass
class FeatureChange:
    """A feature release containing one or more changes."""

    name: str
    description: str
    version: str
    changes: list[Change]


@dataclass
class Conflict:
    """A detected conflict between a feature change and a clinic config."""

    clinic_name: str
    clinic_file: str
    change_description: str
    conflict_type: str  # "breaking", "behavioral", "cosmetic"
    severity_score: int  # 10 for breaking, 3 for behavioral, 1 for cosmetic
    reason: str
    affected_dimension: str


@dataclass
class RolloutCohort:
    """A group of clinics scheduled to receive a feature in the same wave."""

    name: str
    clinics: list[str]
    risk_range: str
    gate: str
    test_cases: list[dict[str, str]] = field(default_factory=list)


@dataclass
class RolloutPlan:
    """The full rollout plan for a feature across all clinics."""

    feature_name: str
    total_clinics: int
    cohorts: list[RolloutCohort]
    risk_scores: dict[str, float]


# ---------------------------------------------------------------------------
# YAML loaders
# ---------------------------------------------------------------------------


def _normalize_province_list(value: Any) -> list[str]:
    """Convert affects_provinces from YAML into a consistent list.

    Handles the case where the value is the string "all" or a list of
    province codes.  Also fixes the YAML boolean quirk for province codes.
    """
    if value is None:
        return ["all"]
    if isinstance(value, bool):
        # A bare True/False means YAML parsed a province code like ON/NO.
        return [_fix_yaml_province(value)]
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [_fix_yaml_province(v) for v in value]
    return ["all"]


def load_clinic(path: str) -> ClinicConfig:
    """Load a single clinic YAML file and return a ClinicConfig."""
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    modules = data.get("modules", [])

    return ClinicConfig(
        name=data["name"],
        province=_fix_yaml_province(data["province"]),
        clinic_type=data["clinic_type"],
        provider_count=data.get("provider_count", 1),
        providers=data.get("providers", []),
        modules=modules,
        connect_settings=data.get("connect_settings") if "ava_connect" in modules else None,
        scribe_settings=data.get("scribe_settings"),
        autochart_settings=data.get("autochart_settings"),
        billing=data.get("billing", []),
        integrations=data.get("integrations", []),
        scheduling=data.get("scheduling", {}),
        role_permissions=data.get("role_permissions", {}),
        templates=data.get("templates", {}),
        panelling=data.get("panelling"),
        file_name=os.path.basename(path),
    )


def load_feature(path: str) -> FeatureChange:
    """Load a feature YAML file and return a FeatureChange."""
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    changes: list[Change] = []
    for entry in data.get("changes", []):
        changes.append(
            Change(
                dimension=entry["dimension"],
                field=entry.get("field"),
                change_type=entry.get("change_type", "modify"),
                description=entry.get("description", ""),
                old_value=entry.get("old_value"),
                new_value=entry.get("new_value"),
                affects_provinces=_normalize_province_list(entry.get("affects_provinces")),
                requires_modules=entry.get("requires_modules", []),
                requires_integrations=entry.get("requires_integrations", []),
                breaks_templates=entry.get("breaks_templates", []),
                permission_changes=entry.get("permission_changes") or None,
            )
        )

    return FeatureChange(
        name=data["name"],
        description=data.get("description", ""),
        version=data.get("version", "0.0"),
        changes=changes,
    )


def load_all_clinics(directory: str = "configs/clinics") -> list[ClinicConfig]:
    """Load every .yaml file in *directory* and return a list of ClinicConfigs."""
    clinics: list[ClinicConfig] = []
    for fname in sorted(os.listdir(directory)):
        if fname.endswith(".yaml") or fname.endswith(".yml"):
            clinics.append(load_clinic(os.path.join(directory, fname)))
    return clinics
