import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Performance
from .services.dashboard_query_service import DashboardQueryService
from .services.performance_service import PerformanceService
from .services.phase_service import PhaseService
from .services.report_service import ReportService

logger = logging.getLogger(__name__)


@login_required(login_url='accounts:login')
def dashboard(request):
    """乖離ダッシュボード（人員不足・時間乖離・Lock 漏れ）"""
    staffing_shortages = DashboardQueryService.get_staffing_shortages()
    schedule_drifts = DashboardQueryService.get_schedule_drifts()
    unlocked_past_slots = DashboardQueryService.get_unlocked_past_slots()
    return render(
        request,
        'performances/dashboard.html',
        {
            'staffing_shortages': staffing_shortages,
            'schedule_drifts': schedule_drifts,
            'unlocked_past_slots': unlocked_past_slots,
        },
    )


@login_required(login_url='accounts:login')
def performance_list(request):
    """公演一覧"""
    performances = PerformanceService.get_performance_list(request.user)
    return render(request, 'performances/list.html', {'performances': performances})


@login_required(login_url='accounts:login')
def performance_create(request):
    """公演作成"""
    users, positions = PerformanceService.get_master_data()

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()

        if not title:
            return render(
                request,
                'performances/create.html',
                {
                    'error': '公演名は必須です。',
                    'users': users,
                    'positions': positions,
                },
            )

        # 担当者データのパース
        # フォームから user_ids[], position_ids[] として送られてくることを想定
        user_ids = request.POST.getlist('user_ids[]')
        position_ids = request.POST.getlist('position_ids[]')
        responsible_staff_data = []

        for uid, pid in zip(user_ids, position_ids, strict=False):
            if uid and pid:
                responsible_staff_data.append({'user_id': int(uid), 'position_id': int(pid)})

        try:
            performance = PerformanceService.create_performance(
                title=title,
                created_by=request.user,
                responsible_staff_data=responsible_staff_data,
                description=request.POST.get('description', ''),
            )
            return redirect('performances:detail', pk=performance.pk)
        except Exception as e:
            return render(
                request,
                'performances/create.html',
                {'error': str(e), 'users': users, 'positions': positions},
            )

    return render(request, 'performances/create.html', {'users': users, 'positions': positions})


@login_required(login_url='accounts:login')
def performance_detail(request, pk):
    """公演詳細（工程・配車一覧）"""
    from datetime import timedelta

    performance = get_object_or_404(Performance, pk=pk)
    phases = PhaseService.get_phases_with_slots(performance)

    # 運行工程を取得（有効なものと、履歴確認用に最近削除されたものも含む）
    vehicle_operations = (
        performance.vehicle_operations.all()
        .prefetch_related('assignments__vehicle', 'deleted_by__profile', 'updated_by__profile')
        .order_by('requested_start')
    )

    # テンプレート側でのグループ化表示を容易にするため、
    # 各車輌がどの日程に紐づいているかを整理
    from collections import defaultdict

    v_map = defaultdict(lambda: defaultdict(list))
    for op in vehicle_operations:
        curr_d = op.requested_start.date()
        end_d = op.requested_end.date()
        while curr_d <= end_d:
            # 割り当てられている車輌ごとに分類
            for assign in op.assignments.all():
                if assign.vehicle:
                    v_map[curr_d.isoformat()][str(assign.vehicle.pk)].append(op)
            curr_d += timedelta(days=1)

    # テンプレート（Django）で defaultdict.items がうまく動かない場合があるため、
    # 完全に dict に変換する
    vehicle_daily_map = {d: dict(v) for d, v in v_map.items()}

    from .models.base import PhaseMaster

    phase_masters = PhaseMaster.objects.all()

    # 有効な車輌マスタを取得
    from .models.vehicle import Vehicle

    vehicles = Vehicle.objects.filter(is_active=True)

    context = {
        'performance': performance,
        'phases': phases,
        'phase_masters': phase_masters,
        'vehicle_operations': vehicle_operations,
        'vehicle_daily_map': vehicle_daily_map,
        'vehicles': vehicles,
    }

    # ガントチャート用の日付リスト生成
    if performance.has_phases and performance.start_date and performance.end_date:
        from datetime import timedelta

        date_range = []
        curr = performance.start_date
        while curr <= performance.end_date:
            date_range.append(curr)
            curr += timedelta(days=1)
        context['date_range'] = date_range

    if not performance.has_phases:
        from .services.phase_service import TEMPLATE_STEPS

        context['template_steps'] = TEMPLATE_STEPS

    return render(
        request,
        'performances/detail.html',
        context,
    )


@login_required(login_url='accounts:login')
@require_POST
def apply_template(request, pk):
    """テンプレート展開（POST のみ受け付ける）"""
    performance = get_object_or_404(Performance, pk=pk)

    try:
        from datetime import date

        from .services.phase_service import TEMPLATE_STEPS

        phase_data_list = []
        for i in range(len(TEMPLATE_STEPS)):
            p_start_date_str = request.POST.get(f'phase_start_date_{i}', '')
            p_end_date_str = request.POST.get(f'phase_end_date_{i}', '')
            p_start_time_str = request.POST.get(f'phase_start_time_{i}', '')
            p_end_time_str = request.POST.get(f'phase_end_time_{i}', '')

            # 開始日または終了日が空の場合は None にする
            p_start_date = date.fromisoformat(p_start_date_str) if p_start_date_str else None
            p_end_date = date.fromisoformat(p_end_date_str) if p_end_date_str else p_start_date

            # 日付が未入力の場合は時間も登録しない
            if not p_start_date:
                p_start_time_str = None
                p_end_time_str = None

            phase_data_list.append((p_start_date, p_end_date, p_start_time_str, p_end_time_str))

        PhaseService.apply_production_template(performance, phase_data_list)
        logger.info(
            f'テンプレート展開完了: performance_id={performance.pk}, user={request.user.email}'
        )
    except Exception as e:
        logger.warning(f'テンプレート展開失敗: {e}')
        from .services.phase_service import TEMPLATE_STEPS

        return render(
            request,
            'performances/detail.html',
            {
                'performance': performance,
                'phases': [],
                'template_steps': TEMPLATE_STEPS,
                'error': str(e),
            },
        )

    return redirect('performances:detail', pk=performance.pk)


@login_required(login_url='accounts:login')
@require_POST
def phase_create(request, pk):
    """工程の個別追加"""
    performance = get_object_or_404(Performance, pk=pk)

    # マスタから選択された名前を取得
    master_id = request.POST.get('master_id')
    from .models.base import PhaseMaster

    master = get_object_or_404(PhaseMaster, pk=master_id)
    name = master.name

    # 既存の最大 order + 1 を取得
    from django.db.models import Max

    max_order = performance.phases.aggregate(Max('order'))['order__max']
    order = (max_order + 1) if max_order is not None else 0

    from .models.base import Phase, PhaseSlot

    phase = Phase.objects.create(performance=performance, name=name, order=order)
    # デフォルトの人員枠を作成
    PhaseSlot.objects.create(phase=phase, requested_staff_count=0)

    logger.info(f'工程追加: performance_id={pk}, phase_id={phase.pk}, user={request.user.email}')
    return redirect('performances:detail', pk=pk)


@login_required(login_url='accounts:login')
@require_POST
def phase_delete(request, pk):
    """工程の個別削除（管理者のみ）"""
    if not request.user.is_staff:
        return HttpResponse('権限がありません。', status=403)

    from .models.base import Phase

    phase = get_object_or_404(Phase, pk=pk)
    performance_id = phase.performance.pk
    phase_name = phase.name
    phase.delete()

    logger.info(
        f'工程削除: performance_id={performance_id}, '
        f'phase_name={phase_name}, user={request.user.email}'
    )
    return redirect('performances:detail', pk=performance_id)


@login_required(login_url='accounts:login')
@require_POST
def phase_reorder(request, pk):
    """工程の並び順を一括更新"""
    performance = get_object_or_404(Performance, pk=pk)
    phase_ids = request.POST.getlist('phase_ids[]')

    if not phase_ids:
        import json

        try:
            data = json.loads(request.body)
            phase_ids = data.get('phase_ids', [])
        except Exception:
            pass

    if phase_ids:
        from django.db import transaction

        from .models.base import Phase

        with transaction.atomic():
            for index, p_id in enumerate(phase_ids):
                Phase.objects.filter(pk=p_id, performance=performance).update(order=index)

        return HttpResponse(status=204)

    return HttpResponseBadRequest('並び順データがありません。')


@login_required(login_url='accounts:login')
@require_POST
def phase_update(request, pk):
    """工程の詳細更新（日程・時間・希望人数）"""
    from datetime import date

    from .models.base import Phase

    phase = get_object_or_404(Phase, pk=pk)

    # 基本情報の更新
    phase.name = request.POST.get('name', phase.name).strip()

    start_date_str = request.POST.get('suggested_start_date', '')
    end_date_str = request.POST.get('suggested_end_date', '')
    phase.suggested_start_date = date.fromisoformat(start_date_str) if start_date_str else None
    phase.suggested_end_date = (
        date.fromisoformat(end_date_str) if end_date_str else phase.suggested_start_date
    )

    # バリデーション
    if (
        phase.suggested_start_date
        and phase.suggested_end_date
        and phase.suggested_start_date > phase.suggested_end_date
    ):
        return HttpResponseBadRequest('開始日は終了日より前の日付にしてください。')

    phase.suggested_start_time = request.POST.get('suggested_start_time') or None
    phase.suggested_end_time = request.POST.get('suggested_end_time') or None
    phase.description = request.POST.get('description', '').strip()
    phase.save()

    # 人員枠（希望人数）の更新 — 最初のスロットを対象とする
    requested_staff_count = request.POST.get('requested_staff_count')
    if requested_staff_count is not None:
        slot = phase.slots.first()
        if slot:
            slot.requested_staff_count = int(requested_staff_count)
            slot.save()

    logger.info(f'工程更新: phase_id={pk}, user={request.user.email}')
    return redirect('performances:detail', pk=phase.performance.pk)


@login_required(login_url='accounts:login')
@require_POST
def vehicle_operation_create(request, pk):
    """車輌手配申請の作成・更新"""
    from datetime import date, datetime, time, timedelta

    from django.db import transaction

    from .models.base import Performance
    from .models.vehicle import Vehicle, VehicleAssignment, VehicleOperation

    performance = get_object_or_404(Performance, pk=pk)

    date_str = request.POST.get('date')
    vehicle_id = request.POST.get('vehicle_id')
    vehicle = get_object_or_404(Vehicle, pk=vehicle_id)
    base_date = date.fromisoformat(date_str)

    # 配列データの取得
    op_ids = request.POST.getlist('op_id[]')
    process_names = request.POST.getlist('process_name[]')
    places = request.POST.getlist('place[]')
    times = request.POST.getlist('time[]')
    staff_counts = request.POST.getlist('staff_count[]')

    with transaction.atomic():
        for i in range(len(process_names)):
            op_id = op_ids[i] if i < len(op_ids) else None
            name = process_names[i].strip()
            place = places[i].strip()
            t_str = times[i]
            staff = staff_counts[i] or 0

            if not name and not place:
                continue

            # 時間の設定
            start_time = time.fromisoformat(t_str) if t_str else time(9, 0)
            start_dt = datetime.combine(base_date, start_time)
            end_dt = start_dt + timedelta(hours=1)

            if op_id and op_id != 'null':
                # 既存レコードの更新
                op = get_object_or_404(VehicleOperation, pk=op_id, performance=performance)
                op.title = name or op.title
                op.requested_start = start_dt
                op.requested_end = end_dt
                op.route_from = place
                op.route_to = place
                op.requested_staff_count = staff
                op.updated_by = request.user
                op.save()

                # 既存アサインの更新（車輌が変更された場合）
                assign = op.assignments.first()
                if assign:
                    assign.vehicle = vehicle
                    assign.save()
                else:
                    VehicleAssignment.objects.create(vehicle_operation=op, vehicle=vehicle)
            else:
                # 新規作成
                op = VehicleOperation.objects.create(
                    performance=performance,
                    title=name or f'車輌工程{i + 1}',
                    requested_start=start_dt,
                    requested_end=end_dt,
                    route_from=place,
                    route_to=place,
                    requested_staff_count=staff,
                )
                VehicleAssignment.objects.create(vehicle_operation=op, vehicle=vehicle)

    logger.info(f'車輌手配（作成・更新）完了: performance_id={pk}, user={request.user.email}')
    return redirect('performances:detail', pk=pk)


@login_required(login_url='accounts:login')
@require_POST
def vehicle_operation_delete(request, pk):
    """運行工程の削除（論理削除）"""
    from django.utils import timezone

    from .models.vehicle import VehicleOperation

    op = get_object_or_404(VehicleOperation, pk=pk)
    performance_id = op.performance.pk

    # 論理削除の実行
    op.is_active = False
    op.deleted_at = timezone.now()
    op.deleted_by = request.user
    op.save()

    logger.info(f'運行工程論理削除完了: vehicle_operation_id={pk}, user={request.user.email}')
    return redirect('performances:detail', pk=performance_id)


@login_required(login_url='accounts:login')
@require_POST
def vehicle_operation_batch_delete(request, pk):
    """運行工程の複数一括削除（論理削除）"""
    from django.utils import timezone

    from .models.base import Performance
    from .models.vehicle import VehicleOperation

    performance = get_object_or_404(Performance, pk=pk)
    op_ids = request.POST.getlist('op_ids[]')

    if not op_ids:
        # 文字列として送られてくる場合（JSからのカンマ区切りなど）
        op_ids_str = request.POST.get('op_ids', '')
        if op_ids_str:
            op_ids = [id_strip for id_strip in op_ids_str.split(',') if id_strip]

    if op_ids:
        VehicleOperation.objects.filter(pk__in=op_ids, performance=performance).update(
            is_active=False, deleted_at=timezone.now(), deleted_by=request.user
        )
        logger.info(
            f'運行工程一括論理削除完了: performance_id={pk}, '
            f'count={len(op_ids)}, user={request.user.email}'
        )

    return redirect('performances:detail', pk=pk)


@login_required(login_url='accounts:login')
@require_POST
def performance_delete(request, pk):
    """公演削除（管理者のみ実行可能）"""
    if not request.user.is_staff:
        return HttpResponse('権限がありません。', status=403)

    performance = get_object_or_404(Performance, pk=pk)
    title = performance.title
    performance.delete()

    logger.info(f'公演削除完了: title={title}, performance_id={pk}, user={request.user.email}')
    return redirect('performances:list')


@login_required(login_url='accounts:login')
def performance_report_pdf(request, pk):
    """公演手配書 PDF ダウンロード（現場スタッフ・ドライバー配布用）"""
    performance = get_object_or_404(Performance, pk=pk)

    try:
        pdf_bytes = ReportService.generate_performance_report(performance)
    except ValidationError as e:
        return HttpResponseBadRequest(str(e))

    filename = f'performance_report_{performance.pk}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required(login_url='accounts:login')
def financial_report_pdf(request, pk):
    """手配実績証明書 PDF ダウンロード（経理提出・PDF 保存用）"""
    performance = get_object_or_404(Performance, pk=pk)

    try:
        pdf_bytes = ReportService.generate_financial_report(performance)
    except ValidationError as e:
        return HttpResponseBadRequest(str(e))

    filename = f'financial_report_{performance.pk}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
