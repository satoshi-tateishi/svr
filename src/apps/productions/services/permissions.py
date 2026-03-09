from apps.accounts.models import UserProfile
from apps.productions.models import ProductionMember


def _get_role(user) -> str | None:
    try:
        return user.profile.system_role
    except UserProfile.DoesNotExist:
        return None


def is_admin(user) -> bool:
    return _get_role(user) == UserProfile.SystemRole.ADMIN


def is_editor(user) -> bool:
    return _get_role(user) == UserProfile.SystemRole.EDITOR


def is_general(user) -> bool:
    return _get_role(user) == UserProfile.SystemRole.GENERAL


def is_viewer(user) -> bool:
    return _get_role(user) == UserProfile.SystemRole.VIEWER


def is_production_member(user, production, roles=None) -> bool:
    qs = ProductionMember.objects.filter(user=user, production=production)
    if roles:
        qs = qs.filter(role__in=roles)
    return qs.exists()


def can_edit_requests(user, production) -> bool:
    if is_admin(user) or is_editor(user):
        return True
    return is_production_member(
        user,
        production,
        roles=[ProductionMember.Role.SOUND_DESIGNER, ProductionMember.Role.CHIEF],
    )


def can_manage_assignments(user) -> bool:
    return is_admin(user) or is_editor(user)


def can_edit_process(user, production) -> bool:
    if is_admin(user) or is_editor(user):
        return True
    return is_production_member(
        user,
        production,
        roles=[ProductionMember.Role.SOUND_DESIGNER, ProductionMember.Role.CHIEF],
    )


def can_view_costs(user) -> bool:
    return is_admin(user) or is_editor(user)
