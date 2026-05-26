"""Acquirer profile audit — age, stale/critical status, and confidence caps.

Evaluates all loaded AcquirerProfile objects against configurable staleness
thresholds and returns a structured audit report. Profiles that exceed
thresholds have their BuyerMandateScore confidence capped accordingly.

Staleness tiers (calendar days since ``profile_as_of``):
- ``"fresh"``    — ≤ 90 days  → no cap applied
- ``"stale"``    — 91–365 days → confidence capped at ``"medium"``
- ``"critical"`` — > 365 days  → confidence capped at ``"low"``

Design notes
------------
- ``AcquirerProfileAuditResult`` is a pure data container with no side effects.
- ``audit_acquirer_profiles`` never raises — missing profiles are noted, not errors.
- ``render_profile_audit`` returns a self-contained Markdown section.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_FRESH_DAYS: int = 90
_STALE_DAYS: int = 365


def _staleness_tier(age_days: int) -> str:
    if age_days <= _FRESH_DAYS:
        return "fresh"
    if age_days <= _STALE_DAYS:
        return "stale"
    return "critical"


def _confidence_cap(tier: str) -> Optional[str]:
    """Return the confidence cap for a given staleness tier.

    Returns None when no cap is needed (fresh profiles).
    """
    if tier == "stale":
        return "medium"
    if tier == "critical":
        return "low"
    return None


# ---------------------------------------------------------------------------
# Per-profile audit item
# ---------------------------------------------------------------------------

@dataclass
class ProfileAuditItem:
    """Audit result for one acquirer profile.

    Parameters
    ----------
    acquirer_id:
        Unique acquirer identifier.
    company_name:
        Human-readable company name.
    profile_as_of:
        Date of the profile's research sources.
    age_days:
        Calendar days between ``profile_as_of`` and ``reference_date``.
    staleness_tier:
        ``"fresh"`` | ``"stale"`` | ``"critical"``
    confidence_cap:
        ``None`` when fresh; ``"medium"`` when stale; ``"low"`` when critical.
    staleness_warning:
        Human-readable warning string when tier != "fresh".
    """

    acquirer_id: str
    company_name: str
    profile_as_of: Optional[date]
    age_days: int
    staleness_tier: str
    confidence_cap: Optional[str]
    staleness_warning: Optional[str]


# ---------------------------------------------------------------------------
# Aggregate audit result
# ---------------------------------------------------------------------------

@dataclass
class AcquirerProfileAuditResult:
    """Aggregated audit across all loaded acquirer profiles.

    Parameters
    ----------
    items:
        One ``ProfileAuditItem`` per audited profile.
    reference_date:
        Date used for age calculations.
    n_fresh:
        Count of profiles at ``"fresh"`` tier.
    n_stale:
        Count of profiles at ``"stale"`` tier.
    n_critical:
        Count of profiles at ``"critical"`` tier.
    overall_confidence_cap:
        Lowest cap across all profiles:
        ``None`` → all fresh, ``"medium"`` → some stale, ``"low"`` → any critical.
    """

    items: list[ProfileAuditItem] = field(default_factory=list)
    reference_date: Optional[date] = None
    n_fresh: int = 0
    n_stale: int = 0
    n_critical: int = 0
    overall_confidence_cap: Optional[str] = None

    def has_stale_profiles(self) -> bool:
        return self.n_stale > 0 or self.n_critical > 0

    def to_dict(self) -> dict:
        return {
            "reference_date": self.reference_date.isoformat() if self.reference_date else None,
            "n_fresh": self.n_fresh,
            "n_stale": self.n_stale,
            "n_critical": self.n_critical,
            "overall_confidence_cap": self.overall_confidence_cap,
            "items": [
                {
                    "acquirer_id": i.acquirer_id,
                    "company_name": i.company_name,
                    "profile_as_of": i.profile_as_of.isoformat() if i.profile_as_of else None,
                    "age_days": i.age_days,
                    "staleness_tier": i.staleness_tier,
                    "confidence_cap": i.confidence_cap,
                    "staleness_warning": i.staleness_warning,
                }
                for i in self.items
            ],
        }


# ---------------------------------------------------------------------------
# Main audit function
# ---------------------------------------------------------------------------

def audit_acquirer_profiles(
    profiles: list,
    *,
    reference_date: Optional[date] = None,
) -> AcquirerProfileAuditResult:
    """Audit a list of AcquirerProfile objects for staleness.

    Parameters
    ----------
    profiles:
        List of ``bve.intelligence.acquirer_profiles.AcquirerProfile`` objects.
        Duck-typed: any object with ``acquirer_id``, ``company_name``, and
        ``profile_as_of`` attributes is accepted.
    reference_date:
        Date for age calculation; defaults to today.

    Returns
    -------
    AcquirerProfileAuditResult
        Aggregated audit result.
    """
    ref = reference_date or date.today()
    items: list[ProfileAuditItem] = []

    for profile in profiles:
        acquirer_id = getattr(profile, "acquirer_id", "unknown")
        company_name = getattr(profile, "company_name", "Unknown")
        profile_as_of = getattr(profile, "profile_as_of", None)

        if profile_as_of is None:
            age_days = _STALE_DAYS + 1  # Treat missing date as critical
            tier = "critical"
            stale_warn = f"Profile '{acquirer_id}' has no profile_as_of date — treated as critical"
        else:
            age_days = (ref - profile_as_of).days
            tier = _staleness_tier(age_days)
            if tier == "fresh":
                stale_warn = None
            elif tier == "stale":
                stale_warn = (
                    f"Profile '{acquirer_id}' is {age_days} days old "
                    f"(>{_FRESH_DAYS}d threshold) — confidence capped at medium"
                )
            else:
                stale_warn = (
                    f"Profile '{acquirer_id}' is {age_days} days old "
                    f"(>{_STALE_DAYS}d threshold) — confidence capped at low"
                )

        items.append(
            ProfileAuditItem(
                acquirer_id=acquirer_id,
                company_name=company_name,
                profile_as_of=profile_as_of,
                age_days=age_days,
                staleness_tier=tier,
                confidence_cap=_confidence_cap(tier),
                staleness_warning=stale_warn,
            )
        )

    n_fresh = sum(1 for i in items if i.staleness_tier == "fresh")
    n_stale = sum(1 for i in items if i.staleness_tier == "stale")
    n_critical = sum(1 for i in items if i.staleness_tier == "critical")

    if n_critical > 0:
        overall_cap = "low"
    elif n_stale > 0:
        overall_cap = "medium"
    else:
        overall_cap = None

    return AcquirerProfileAuditResult(
        items=items,
        reference_date=ref,
        n_fresh=n_fresh,
        n_stale=n_stale,
        n_critical=n_critical,
        overall_confidence_cap=overall_cap,
    )


def audit_profiles_from_yaml(
    yaml_path: Optional[str] = None,
    *,
    reference_date: Optional[date] = None,
) -> AcquirerProfileAuditResult:
    """Load acquirer profiles from YAML and audit them.

    Parameters
    ----------
    yaml_path:
        Path to ``pipeline_gaps.yaml``. Defaults to
        ``research/mna/pipeline_gaps.yaml``.
    reference_date:
        Date for age calculation; defaults to today.

    Returns
    -------
    AcquirerProfileAuditResult
    """
    from pathlib import Path

    default_path = Path("research") / "mna" / "pipeline_gaps.yaml"
    path = Path(yaml_path) if yaml_path else default_path

    if not path.exists():
        return AcquirerProfileAuditResult(
            reference_date=reference_date or date.today(),
        )

    try:
        from bve.intelligence.acquirer_profiles import AcquirerProfileLoader
        loader = AcquirerProfileLoader(str(path))
        profiles = loader.all()
        return audit_acquirer_profiles(profiles, reference_date=reference_date)
    except Exception:
        return AcquirerProfileAuditResult(
            reference_date=reference_date or date.today(),
        )


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render_profile_audit(result: AcquirerProfileAuditResult) -> str:
    """Render an AcquirerProfileAuditResult as a Markdown section."""
    na = "Not available"
    ref_str = result.reference_date.isoformat() if result.reference_date else na

    lines = [
        "### Acquirer Profile Audit",
        "",
        f"**Reference date:** {ref_str}  |  "
        f"**Fresh:** {result.n_fresh}  |  "
        f"**Stale:** {result.n_stale}  |  "
        f"**Critical:** {result.n_critical}",
    ]

    if result.overall_confidence_cap:
        lines.append(
            f"\n> ⚠ Overall confidence cap: **{result.overall_confidence_cap}** "
            f"({result.n_stale} stale, {result.n_critical} critical profiles)"
        )

    if not result.items:
        lines += ["", "_No acquirer profiles found._", ""]
        return "\n".join(lines)

    lines += [
        "",
        "| Acquirer | Profile As Of | Age (days) | Status | Confidence Cap |",
        "|---|---|---|---|---|",
    ]

    for item in result.items:
        as_of_str = item.profile_as_of.isoformat() if item.profile_as_of else na
        cap_str = item.confidence_cap or "—"
        tier_emoji = {"fresh": "✓", "stale": "⚠", "critical": "✗"}.get(
            item.staleness_tier, item.staleness_tier
        )
        lines.append(
            f"| {item.company_name} | {as_of_str} | {item.age_days} | "
            f"{tier_emoji} {item.staleness_tier} | {cap_str} |"
        )

    lines.append("")
    return "\n".join(lines)
