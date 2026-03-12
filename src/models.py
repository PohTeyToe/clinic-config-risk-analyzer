"""Data models and YAML loaders for the Clinic Configuration Risk Analyzer."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
    providers: List[str]
    modules: List[str]
    connect_settings: Optional[Dict[str, Any]]
    scribe_settings: Optional[Dict[str, Any]]
    autochart_settings: Optional[Dict[str, Any]]
    billing: List[str]
    integrations: List[str]
    scheduling: Dict[str, Any]
    role_permissions: Dict[str, List[str]]
    templates: Dict[str, List[str]]
    panelling: Optional[Dict[str, Any]]
    file_name: str


@dataclass
class Change:
    """A single change within a feature release."""

    dimension: str
    field: Optional[str]
    change_type: str  # add / modify / remove / rename
    description: str
    old_value: Optional[Any]
    new_value: Optional[Any]
    affects_provinces: List[str]  # province codes or ["all"]
    requires_modules: List[str]
    requires_integrations: List[str]
    breaks_templates: List[str]
    permission_changes: Optional[Dict[str, str]]


@dataclass
class FeatureChange:
    """A feature release containing one or more changes."""

    name: str
    description: str
    version: str
    changes: List[Change]


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
    clinics: List[str]
    risk_range: str
    gate: str
    test_cases: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class RolloutPlan:
    """The full rollout plan for a feature across all clinics."""

    feature_name: str
    total_clinics: int
    cohorts: List[RolloutCohort]
    risk_scores: Dict[str, float]


# ---------------------------------------------------------------------------
# YAML loaders
# ---------------------------------------------------------------------------

def _normalize_province_list(value: Any) -> List[str]:
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
    with open(path, "r", encoding="utf-8") as fh:
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
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    changes: List[Change] = []
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


def load_all_clinics(directory: str = "configs/clinics") -> List[ClinicConfig]:
    """Load every .yaml file in *directory* and return a list of ClinicConfigs."""
    clinics: List[ClinicConfig] = []
    for fname in sorted(os.listdir(directory)):
        if fname.endswith(".yaml") or fname.endswith(".yml"):
            clinics.append(load_clinic(os.path.join(directory, fname)))
    return clinics
