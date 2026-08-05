"""
Consignee resolution.

Given a project type and a community, returns the entity that materials
get consigned to. SHEP -> the project's assigned consultant. Cost Sharing
and Streetlights -> the constituency MP. Other / unknown roles -> None
with a clear reason.

Resolution is intentionally a pure function so it's easy to unit-test and
re-call from any view layer.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ResolvedConsignee:
    """
    Outcome of a consignee resolution. Always returned (never None) so
    callers can switch on `kind` without null-checks. When resolution
    fails, kind == 'unresolved' and `reason` explains why.
    """
    kind: str          # 'consultant' | 'mp' | 'unresolved'
    name: str          # Human-readable display name; '' when unresolved
    detail: str        # Constituency for MPs, firm for consultants, '' otherwise
    contact_email: str = ''
    contact_phone: str = ''
    reason: str = ''   # Populated only when kind == 'unresolved'

    @property
    def is_resolved(self) -> bool:
        return self.kind in ('consultant', 'mp')

    @property
    def display_label(self) -> str:
        """The user-facing label that goes on memos and release letters."""
        if self.kind == 'mp':
            return 'Hon. Member of Parliament'
        if self.kind == 'consultant':
            return 'Consultant'
        return 'Consignee'

    def render(self) -> str:
        """Single-line rendering used in document bodies and dashboards."""
        if not self.is_resolved:
            return f"[unresolved: {self.reason}]"
        if self.kind == 'mp':
            return f"{self.name} ({self.detail})" if self.detail else self.name
        return f"{self.name}, {self.detail}" if self.detail else self.name


def resolve_consignee(project_type, community=None, project=None) -> ResolvedConsignee:
    """
    Resolve who materials get consigned to.

    Args:
        project_type: a ProjectType instance (or None).
        community: optional Community / SHEPCommunity instance. Used to look
            up the constituency MP.
        project: optional Project instance. Used for SHEP to find the
            project's assigned consultant.

    Returns ResolvedConsignee. Never raises -- unresolvable inputs return
    a kind='unresolved' result with a reason set.
    """
    if project_type is None:
        return ResolvedConsignee(
            kind='unresolved', name='', detail='',
            reason='No project type supplied',
        )

    role = getattr(project_type, 'consignee_role', 'other')

    if role == 'consultant':
        return _resolve_consultant(project_type, community, project)
    if role == 'mp':
        return _resolve_mp(project_type, community)
    return ResolvedConsignee(
        kind='unresolved', name='', detail='',
        reason=f"Project type '{project_type}' has consignee_role='{role}'; no resolver available",
    )


def _resolve_consultant(project_type, community, project) -> ResolvedConsignee:
    """
    SHEP-style resolution: the consultant covering the community's region.

    Resolution priority:
      1. Community.project_consultant FK (explicit override)
      2. ProjectConsultant where district == community.district (active)
      3. ProjectConsultant where region == community.region (active)
      4. Legacy: Project.consultant_fk (if a Project instance was supplied)
      5. Legacy: Project.consultant free-text field
      6. Unresolved with a clear reason

    Mirrors the MP fallback chain so SHEP and MP-routed projects feel
    symmetrical to the user.
    """
    from Inventory.models import ProjectConsultant

    # Priority 1: explicit FK on the community.
    if community is not None:
        explicit = getattr(community, 'project_consultant', None)
        if explicit is not None and getattr(explicit, 'active', False):
            return ResolvedConsignee(
                kind='consultant',
                name=explicit.name,
                detail=explicit.firm,
                contact_email=explicit.contact_email,
                contact_phone=explicit.contact_phone,
            )

    # Priority 2: area match — the consultant whose Area contains this
    # community's region (the primary binding). Legacy region/district on the
    # consultant row are only used when no area covers the region.
    if community is not None:
        region = getattr(community, 'region', None) or ''
        district = getattr(community, 'district', None) or ''

        queryset = ProjectConsultant.objects.filter(active=True)
        candidate = None
        if region:
            from Inventory.models import Area
            area = Area.objects.filter(regions__region__iexact=region).first()
            if area is not None:
                candidate = queryset.filter(area=area).first()
        # Legacy fallbacks.
        if candidate is None and district:
            candidate = queryset.filter(district__iexact=district).first()
        if candidate is None and region:
            candidate = queryset.filter(region__iexact=region).first()

        if candidate is not None:
            return ResolvedConsignee(
                kind='consultant',
                name=candidate.name,
                detail=candidate.firm,
                contact_email=candidate.contact_email,
                contact_phone=candidate.contact_phone,
            )

    # Priorities 4 + 5: legacy Project-based fallbacks (kept for back-compat
    # with rows created before the region-based resolver).
    if project is not None:
        consultant_fk = getattr(project, 'consultant_fk', None)
        if isinstance(consultant_fk, ProjectConsultant) and consultant_fk.active:
            return ResolvedConsignee(
                kind='consultant',
                name=consultant_fk.name,
                detail=consultant_fk.firm,
                contact_email=consultant_fk.contact_email,
                contact_phone=consultant_fk.contact_phone,
            )
        legacy_name = getattr(project, 'consultant', '') or ''
        if legacy_name:
            return ResolvedConsignee(
                kind='consultant',
                name=legacy_name,
                detail='',
            )

    # Priority 6: unresolved.
    region = getattr(community, 'region', '') if community else ''
    district = getattr(community, 'district', '') if community else ''
    return ResolvedConsignee(
        kind='unresolved', name='', detail='',
        reason=(
            f"No active consultant found for region='{region}' / district='{district}'. "
            "Add a consultant for this region via Project Consultants in admin, "
            "or bind one explicitly on the community."
        ),
    )


def _resolve_mp(project_type, community) -> ResolvedConsignee:
    """
    Cost Sharing / Streetlights: look up the MP for the community.

    Resolution priority:
      1. Explicit binding via community.member_of_parliament FK (active only)
      2. constituency string match on community.constituency
      3. district match
      4. region match
      5. unresolved with a clear reason

    The explicit FK wins because operators may have manually pinned the
    correct MP for a community whose constituency string is missing or
    doesn't match the MP's record (typo, alternate spelling, redistricting).
    """
    from Inventory.models import MemberOfParliament

    if community is None:
        return ResolvedConsignee(
            kind='unresolved', name='', detail='',
            reason='No community supplied; cannot identify constituency',
        )

    # Priority 1: explicit FK binding on the community.
    explicit_mp = getattr(community, 'member_of_parliament', None)
    if explicit_mp is not None and getattr(explicit_mp, 'active', False):
        return ResolvedConsignee(
            kind='mp',
            name=explicit_mp.display_name,
            detail=explicit_mp.constituency,
            contact_email=explicit_mp.email,
            contact_phone=explicit_mp.phone,
        )

    # Fallback chain: string-based constituency / district / region match.
    constituency = getattr(community, 'constituency', None) or ''
    region = getattr(community, 'region', None) or ''
    district = getattr(community, 'district', None) or ''

    queryset = MemberOfParliament.objects.filter(active=True)

    candidate: Optional[MemberOfParliament] = None
    if constituency:
        candidate = queryset.filter(constituency__iexact=constituency).first()
    if candidate is None and district:
        candidate = queryset.filter(district__iexact=district).first()
    if candidate is None and region:
        candidate = queryset.filter(region__iexact=region).first()

    if candidate is None:
        return ResolvedConsignee(
            kind='unresolved', name='', detail='',
            reason=(
                f"No active MP found for constituency='{constituency}' / "
                f"district='{district}' / region='{region}'. "
                "Bind one explicitly via the community's MP field, or add an MP via admin."
            ),
        )

    return ResolvedConsignee(
        kind='mp',
        name=candidate.display_name,
        detail=candidate.constituency,
        contact_email=candidate.email,
        contact_phone=candidate.phone,
    )
