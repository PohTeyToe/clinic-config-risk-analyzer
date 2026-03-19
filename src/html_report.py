"""Generate a self-contained HTML report for stakeholder review.

Usage:
    python -m src.html_report features/prescribing_redesign.yaml report.html
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from .conflict_detector import detect_conflicts
from .models import ClinicConfig, Conflict, FeatureChange, load_all_clinics, load_feature
from .rollout_planner import create_rollout_plan


def _build_clinic_data(
    clinics: list[ClinicConfig],
    conflicts: dict[str, list[Conflict]],
    risk_scores: dict[str, float],
) -> list[dict[str, Any]]:
    """Build a list of clinic dicts for the template."""
    data = []
    for clinic in clinics:
        clinic_conflicts = conflicts.get(clinic.name, [])
        breaking = sum(1 for c in clinic_conflicts if c.conflict_type == "breaking")
        data.append(
            {
                "name": clinic.name,
                "province": clinic.province,
                "risk_score": risk_scores.get(clinic.name, 0),
                "breaking": breaking,
                "conflicts": [
                    {
                        "conflict_type": c.conflict_type,
                        "affected_dimension": c.affected_dimension,
                        "reason": c.reason,
                    }
                    for c in clinic_conflicts
                ],
            }
        )
    # Sort by risk score descending.
    data.sort(key=lambda d: float(d["risk_score"]), reverse=True)  # type: ignore[arg-type]
    return data


def generate_html_report(
    feature: FeatureChange,
    clinics: list[ClinicConfig],
    output_path: str | Path,
) -> Path:
    """Generate an HTML report and write it to *output_path*."""
    conflicts = detect_conflicts(clinics, feature)
    plan = create_rollout_plan(feature, clinics, conflicts)

    all_conflicts = [c for lst in conflicts.values() for c in lst]
    breaking_count = sum(1 for c in all_conflicts if c.conflict_type == "breaking")
    behavioral_count = sum(1 for c in all_conflicts if c.conflict_type == "behavioral")
    cosmetic_count = sum(1 for c in all_conflicts if c.conflict_type == "cosmetic")

    provinces = sorted({c.province for c in clinics})
    clinic_data = _build_clinic_data(clinics, conflicts, plan.risk_scores)

    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    template = env.get_template("report.html.j2")

    html = template.render(
        feature=feature,
        total_clinics=len(clinics),
        breaking_count=breaking_count,
        behavioral_count=behavioral_count,
        cosmetic_count=cosmetic_count,
        provinces=provinces,
        clinic_data=clinic_data,
        plan=plan,
    )

    out = Path(output_path)
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m src.html_report <feature_yaml> <output.html>")
        sys.exit(1)

    feature_path = sys.argv[1]
    out_path = sys.argv[2]
    feature = load_feature(feature_path)
    clinics = load_all_clinics()
    result = generate_html_report(feature, clinics, out_path)
    print(f"Report generated: {result}")
