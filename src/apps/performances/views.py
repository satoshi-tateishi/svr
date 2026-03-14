from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.productions.forms import VehicleAssignmentForm
from apps.productions.models import VehicleAssignment, VehicleRequest
from apps.productions.services.permissions import can_manage_assignments

from .services.dashboard_query_service import DashboardQueryService


@login_required(login_url='accounts:login')
def performance_root(request):
    """旧 /performances/ 導線はダッシュボードへ集約"""
    return redirect('performances:dashboard')


@login_required(login_url='accounts:login')
def dashboard(request):
    """乖離ダッシュボード（人員不足・時間乖離・Lock 漏れ）"""
    staffing_shortages = DashboardQueryService.get_staffing_shortages()
    schedule_drifts = DashboardQueryService.get_schedule_drifts()
    unlocked_past_slots = DashboardQueryService.get_unlocked_past_slots()
    return render(
        request,
        'production_management/dashboard.html',
        {
            'staffing_shortages': staffing_shortages,
            'schedule_drifts': schedule_drifts,
            'unlocked_past_slots': unlocked_past_slots,
        },
    )


@login_required(login_url='accounts:login')
def production_vehicle_assignment_dashboard(request):
    """Production 横断の車両手配管理一覧"""
    if not can_manage_assignments(request.user):
        return HttpResponseForbidden('手配管理の権限がありません。')

    vehicle_requests = VehicleRequest.objects.select_related(
        'process_day__process__production',
        'process_day__process_type',
        'requested_vehicle',
    )
    for vr in vehicle_requests:
        VehicleAssignment.objects.get_or_create(vehicle_request=vr)

    assignments = VehicleAssignment.objects.select_related(
        'vehicle_request__process_day__process__production',
        'vehicle_request__process_day__process_type',
        'vehicle_request__requested_vehicle',
        'assigned_vehicle',
    ).order_by(
        'vehicle_request__process_day__process__production__title',
        'vehicle_request__process_day__date',
        'vehicle_request__requested_time',
    )
    return render(
        request,
        'production_management/production_vehicle_assignment_dashboard.html',
        {'assignments': assignments},
    )


@login_required(login_url='accounts:login')
def production_vehicle_assignment_edit(request, pk):
    """Production 横断の車両手配編集モーダル"""
    if not can_manage_assignments(request.user):
        return HttpResponseForbidden('手配管理の権限がありません。')

    vr = get_object_or_404(VehicleRequest, pk=pk)
    assignment, _ = VehicleAssignment.objects.get_or_create(vehicle_request=vr)

    if request.method == 'POST':
        form = VehicleAssignmentForm(request.POST, instance=assignment)
        if form.is_valid():
            form.save()
            response = HttpResponse()
            response['HX-Redirect'] = reverse('performances:production_vehicle_assignments')
            return response
        return render(
            request,
            'production_management/production_vehicle_assignment_form.html',
            {
                'vr': vr,
                'assignment': assignment,
                'form': form,
                'error_message': 'エラーが発生しました。入力内容を確認してください。',
            },
        )

    form = VehicleAssignmentForm(instance=assignment)
    return render(
        request,
        'production_management/production_vehicle_assignment_form.html',
        {'vr': vr, 'assignment': assignment, 'form': form},
    )
