from django.shortcuts import get_object_or_404

from .models import ProcessDay
from .services.permission_response import permission_denied_response
from .services.permissions import can_edit_requests, can_manage_assignments


class RequestEditPermissionMixin:
    """ProcessDay から Production を取得して can_edit_requests を確認する Mixin"""

    def dispatch(self, request, *args, **kwargs):
        day_pk = kwargs.get('day_pk')
        day = get_object_or_404(ProcessDay.objects.select_related('process__production'), pk=day_pk)
        production = day.process.production
        if not can_edit_requests(request.user, production):
            return permission_denied_response(request, '手配申請の編集権限がありません。')
        return super().dispatch(request, *args, **kwargs)


class AssignmentManagePermissionMixin:
    """can_manage_assignments を確認する Mixin"""

    def dispatch(self, request, *args, **kwargs):
        if not can_manage_assignments(request.user):
            return permission_denied_response(request, '手配管理の権限がありません。')
        return super().dispatch(request, *args, **kwargs)
