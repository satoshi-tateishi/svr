import json
from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, View

from apps.performances.models.vehicle import Vehicle

from .forms import (
    ProcessDayForm,
    ProductionForm,
    ProductionMemberForm,
    StaffRequestForm,
    VehicleAssignmentForm,
)
from .mixins import (
    AssignmentManagePermissionMixin,
    ProcessEditPermissionMixin,
    RequestEditPermissionMixin,
)
from .models import (
    Position,
    Process,
    ProcessDay,
    ProcessRequestUnit,
    ProcessType,
    Production,
    ProductionMember,
    ProductionTemplate,
    StaffRequest,
    VehicleAssignment,
    VehicleRequest,
)
from .templates import (
    BLOCK_POSITION_MAP,
    BLOCK_PROCESS_TYPE_MAP,
    SETUP_BLOCKS,
)

TRAVEL_BLOCK_KEYS = {'travel_load', 'travel_unload'}


def _has_staff_rows(rows):
    return any(str(row.get('qty') or '').strip() for row in rows or [])


def _build_staff_rows(block_key, staff_requests):
    position_map = BLOCK_POSITION_MAP.get(block_key, {})
    staff_by_slug = {sr.position.slug: sr for sr in staff_requests}
    rows = []
    for slug, label in position_map.items():
        staff_request = staff_by_slug.get(slug)
        if not staff_request:
            continue
        rows.append(
            {
                'label': (
                    staff_request.process_request_unit.get_setup_label_display()
                    if block_key == 'theatre_setup' and slug == 'setup-crew'
                    else label
                ),
                'qty': staff_request.quantity,
                'include_self': staff_request.include_self,
            }
        )
    return rows


def _build_process_blocks(processes_qs):
    """工程ブロック表示用データ構造を構築する。

    processes_qs は prefetch_related('days__staff_requests__position',
    'days__vehicle_requests__requested_vehicle') 済みであること。

    将来: BLOCK_POSITION_MAP は apps/productions/templates.py にあるが、
    責務としては constants / definitions モジュールへ寄せる余地がある。
    """
    result = []
    for proc in processes_qs:
        block_key = proc.block_key
        has_final_performance = bool(
            block_key == 'travel_unload'
            and (proc.final_performance_load_out_date or proc.final_performance_location)
        )
        units = []
        for unit in proc.request_units.all():
            vehicle_request = getattr(unit, 'vehicle_request', None)
            staff_requests = list(unit.staff_requests.all())
            units.append(
                {
                    'unit': unit,
                    'unit_type': unit.unit_type,
                    'work_date': unit.work_date,
                    'start_time': unit.start_time,
                    'end_time': unit.end_time,
                    'note': unit.note,
                    'setup_label': unit.setup_label,
                    'setup_label_display': unit.get_setup_label_display(),
                    'vehicle_request': vehicle_request,
                    'staff_rows': _build_staff_rows(block_key, staff_requests),
                }
            )

        result.append(
            {
                'process': proc,
                'block_key': block_key,
                'units': units,
                'has_final_performance': has_final_performance,
            }
        )
    return result


class StaffRequestBulkEditView(RequestEditPermissionMixin, LoginRequiredMixin, View):
    """人員手配の一括編集（モーダル用・Alpine.js使用）"""

    def get(self, request, day_pk):
        day = get_object_or_404(ProcessDay, pk=day_pk)
        # 既存の手配を取得（初期値）
        raw_requests = day.staff_requests.all().values(
            'position_id', 'quantity', 'start_time', 'end_time', 'note'
        )
        requests_data = [
            {
                'position_id': r['position_id'],
                'quantity': r['quantity'],
                'start_time': str(r['start_time'])[:5] if r['start_time'] else '',
                'end_time': str(r['end_time'])[:5] if r['end_time'] else '',
                'note': r['note'],
            }
            for r in raw_requests
        ]
        # ポジションマスタ
        positions = Position.objects.all().order_by('order')

        return render(
            request,
            'productions/unused/staff_request_bulk_form.html',
            {
                'day': day,
                'initial_requests': requests_data,
                'positions': positions,
            },
        )

    def post(self, request, day_pk):
        day = get_object_or_404(ProcessDay, pk=day_pk)
        data_json = request.POST.get('requests_json', '[]')

        # 効率化のため、ポジションマスタを先にマップ化・IDセット化しておく
        positions = Position.objects.all().order_by('order')
        position_map = {p.id: p.name for p in positions}
        valid_position_ids = set(position_map.keys())

        # 再描画用の共通コンテキスト（エラー時用）
        error_context = {
            'day': day,
            'positions': positions,
        }

        try:
            submitted_data = json.loads(data_json)
            error_context['initial_requests'] = submitted_data
        except json.JSONDecodeError:
            error_context['error_message'] = 'データの形式が不正です。'
            return render(request, 'productions/unused/staff_request_bulk_form.html', error_context)

        # 1. 有効な行のみ抽出・バリデーション（ポジション未選択の行は無視）
        valid_items = []

        for item in submitted_data:
            raw_pos_id = item.get('position_id')
            if not raw_pos_id:
                continue

            try:
                pos_id = int(raw_pos_id)
                qty = int(item.get('quantity') or 0)
            except (ValueError, TypeError):
                error_context['error_message'] = '入力内容が不正です。'
                return render(
                    request,
                    'productions/unused/staff_request_bulk_form.html',
                    error_context,
                )

            # ポジションの実在確認
            if pos_id not in valid_position_ids:
                error_context['error_message'] = f'不正なポジションIDです (ID:{pos_id})。'
                return render(
                    request,
                    'productions/unused/staff_request_bulk_form.html',
                    error_context,
                )

            # 数量チェック
            if qty < 1:
                pos_name = position_map.get(pos_id)
                error_context['error_message'] = f'「{pos_name}」は1名以上で入力してください。'
                return render(
                    request,
                    'productions/unused/staff_request_bulk_form.html',
                    error_context,
                )

            # 時間帯のパース
            raw_start = (item.get('start_time') or '').strip() or None
            raw_end = (item.get('end_time') or '').strip() or None

            pos_name = position_map.get(pos_id)

            # end_time のみ入力はエラー
            if raw_end and not raw_start:
                error_context['error_message'] = (
                    f'「{pos_name}」：終了時間のみの入力はできません。開始時間も入力してください。'
                )
                return render(
                    request,
                    'productions/unused/staff_request_bulk_form.html',
                    error_context,
                )

            # start_time > end_time はエラー
            if raw_start and raw_end and raw_start >= raw_end:
                error_context['error_message'] = (
                    f'「{pos_name}」：開始時間は終了時間より前にしてください。'
                )
                return render(
                    request,
                    'productions/unused/staff_request_bulk_form.html',
                    error_context,
                )

            valid_items.append(
                {
                    'position_id': pos_id,
                    'quantity': qty,
                    'start_time': raw_start,
                    'end_time': raw_end,
                    'note': (item.get('note') or '').strip(),
                }
            )

        # 2. 保存処理（全削除 → bulk_create で一括置換）
        with transaction.atomic():
            day.staff_requests.all().delete()
            StaffRequest.objects.bulk_create(
                [
                    StaffRequest(
                        process_day=day,
                        position_id=item['position_id'],
                        quantity=item['quantity'],
                        start_time=item['start_time'],
                        end_time=item['end_time'],
                        note=item['note'],
                    )
                    for item in valid_items
                ]
            )

        # 3. 成功時は全体リダイレクト
        response = HttpResponse()
        production_id = day.process.production.id
        response['HX-Redirect'] = reverse('productions:detail', kwargs={'pk': production_id})
        return response


class PreviousStaffRequestView(LoginRequiredMixin, View):
    """前日の人員手配を取得する（JSON用）"""

    def get(self, request, day_pk):
        day = get_object_or_404(ProcessDay, pk=day_pk)

        # 同一 Production 内で現在の日付より前、かつ最も近い日付の ProcessDay を取得
        previous_day = (
            ProcessDay.objects.filter(
                process__production=day.process.production,
                date__lt=day.date,
            )
            .order_by('-date', '-id')
            .first()
        )

        if not previous_day:
            return JsonResponse(
                {
                    'source_date': None,
                    'requests': [],
                }
            )

        # その日の StaffRequest を取得（start_time / end_time を含む）
        raw_requests = previous_day.staff_requests.all().values(
            'position_id',
            'quantity',
            'start_time',
            'end_time',
            'note',
        )
        requests_data = [
            {
                'position_id': r['position_id'],
                'quantity': r['quantity'],
                'start_time': str(r['start_time'])[:5] if r['start_time'] else '',
                'end_time': str(r['end_time'])[:5] if r['end_time'] else '',
                'note': r['note'],
            }
            for r in raw_requests
        ]

        return JsonResponse(
            {
                'source_date': previous_day.date.strftime('%Y/%m/%d'),
                'requests': requests_data,
            }
        )


class VehicleRequestBulkEditView(RequestEditPermissionMixin, LoginRequiredMixin, View):
    """車両申請の一括編集（モーダル用・Alpine.js使用）"""

    def get(self, request, day_pk):
        day = get_object_or_404(ProcessDay, pk=day_pk)
        # 既存の申請を取得（初期値）
        raw_requests = day.vehicle_requests.all().values(
            'requested_vehicle_id',
            'request_kind',
            'requested_time',
            'arrival_requested_time',
            'route_from',
            'route_to',
            'note',
        )
        requests_data = [
            {
                'requested_vehicle_id': r['requested_vehicle_id'],
                'request_kind': r['request_kind'],
                'requested_time': str(r['requested_time'])[:5] if r['requested_time'] else '',
                'arrival_requested_time': (
                    str(r['arrival_requested_time'])[:5] if r['arrival_requested_time'] else ''
                ),
                'route_from': r['route_from'],
                'route_to': r['route_to'],
                'note': r['note'],
            }
            for r in raw_requests
        ]
        # 有効な車両マスタ
        vehicles = Vehicle.objects.filter(is_active=True).order_by('order')

        return render(
            request,
            'productions/unused/vehicle_request_bulk_form.html',
            {
                'day': day,
                'initial_requests': requests_data,
                'vehicles': vehicles,
            },
        )

    def post(self, request, day_pk):
        day = get_object_or_404(ProcessDay, pk=day_pk)
        data_json = request.POST.get('requests_json', '[]')

        vehicles = Vehicle.objects.filter(is_active=True).order_by('order')
        vehicle_map = {v.id: v.name for v in vehicles}
        valid_vehicle_ids = set(vehicle_map.keys())

        # エラー時再描画用コンテキスト
        error_context = {
            'day': day,
            'vehicles': vehicles,
        }

        try:
            submitted_data = json.loads(data_json)
            error_context['initial_requests'] = submitted_data
        except json.JSONDecodeError:
            error_context['error_message'] = 'データの形式が不正です。'
            return render(
                request,
                'productions/unused/vehicle_request_bulk_form.html',
                error_context,
            )

        # 有効行の抽出とバリデーション
        valid_items = []
        valid_request_kinds = {c[0] for c in VehicleRequest.RequestKind.choices}

        for item in submitted_data:
            raw_vehicle_id = item.get('requested_vehicle_id')
            if not raw_vehicle_id:
                continue

            try:
                vehicle_id = int(raw_vehicle_id)
            except (ValueError, TypeError):
                error_context['error_message'] = '入力内容が不正です。'
                return render(
                    request,
                    'productions/unused/vehicle_request_bulk_form.html',
                    error_context,
                )

            if vehicle_id not in valid_vehicle_ids:
                error_context['error_message'] = f'不正な車両IDです (ID:{vehicle_id})。'
                return render(
                    request,
                    'productions/unused/vehicle_request_bulk_form.html',
                    error_context,
                )

            # request_kind のバリデーション：未指定は load_in、不正値はエラー
            raw_kind = item.get('request_kind') or VehicleRequest.RequestKind.LOAD_IN
            if raw_kind not in valid_request_kinds:
                error_context['error_message'] = f'申請種別の値が不正です（{raw_kind}）。'
                return render(
                    request,
                    'productions/unused/vehicle_request_bulk_form.html',
                    error_context,
                )

            raw_time = item.get('requested_time') or None
            raw_arrival_time = item.get('arrival_requested_time') or None
            valid_items.append(
                {
                    'requested_vehicle_id': vehicle_id,
                    'request_kind': raw_kind,
                    'requested_time': raw_time if raw_time else None,
                    'arrival_requested_time': raw_arrival_time if raw_arrival_time else None,
                    'route_from': (item.get('route_from') or '').strip(),
                    'route_to': (item.get('route_to') or '').strip(),
                    'note': (item.get('note') or '').strip(),
                }
            )

        # トランザクション内で一括置換
        with transaction.atomic():
            day.vehicle_requests.all().delete()
            VehicleRequest.objects.bulk_create(
                [
                    VehicleRequest(
                        process_day=day,
                        requested_vehicle_id=item['requested_vehicle_id'],
                        request_kind=item['request_kind'],
                        requested_time=item['requested_time'],
                        arrival_requested_time=item['arrival_requested_time'],
                        route_from=item['route_from'],
                        route_to=item['route_to'],
                        note=item['note'],
                    )
                    for item in valid_items
                ]
            )

        response = HttpResponse()
        production_id = day.process.production.id
        response['HX-Redirect'] = reverse('productions:detail', kwargs={'pk': production_id})
        return response


class PreviousVehicleRequestView(LoginRequiredMixin, View):
    """直近の車両申請を取得する（JSON用）"""

    def get(self, request, day_pk):
        day = get_object_or_404(ProcessDay, pk=day_pk)

        # 同一 Production 内で現在日より前かつ車両申請が1件以上ある、最も近い ProcessDay を取得
        # vehicle_requests__isnull=False で申請ありの日だけに絞り、distinct() で重複除去
        previous_day = (
            ProcessDay.objects.filter(
                process__production=day.process.production,
                date__lt=day.date,
                vehicle_requests__isnull=False,
            )
            .distinct()
            .order_by('-date', '-id')
            .first()
        )

        if not previous_day:
            return JsonResponse({'source_date': None, 'requests': []})

        raw_requests = previous_day.vehicle_requests.all().values(
            'requested_vehicle_id',
            'request_kind',
            'requested_time',
            'arrival_requested_time',
            'route_from',
            'route_to',
            'note',
        )
        requests_data = [
            {
                'requested_vehicle_id': r['requested_vehicle_id'],
                'request_kind': r['request_kind'],
                'requested_time': str(r['requested_time'])[:5] if r['requested_time'] else '',
                'arrival_requested_time': (
                    str(r['arrival_requested_time'])[:5] if r['arrival_requested_time'] else ''
                ),
                'route_from': r['route_from'],
                'route_to': r['route_to'],
                'note': r['note'],
            }
            for r in raw_requests
        ]

        return JsonResponse(
            {
                'source_date': previous_day.date.strftime('%Y/%m/%d'),
                'requests': requests_data,
            }
        )


class StaffRequestEditView(LoginRequiredMixin, View):
    """人員手配の追加・編集（モーダル用）"""

    def get(self, request, day_pk):
        day = get_object_or_404(ProcessDay, pk=day_pk)
        request_pk = request.GET.get('request_pk')

        instance = None
        if request_pk:
            # その日に属するレコードであることを保証
            instance = StaffRequest.objects.filter(pk=request_pk, process_day=day).first()

        form = StaffRequestForm(instance=instance)
        return render(
            request,
            'productions/unused/staff_request_form.html',
            {'day': day, 'form': form, 'instance': instance},
        )

    def post(self, request, day_pk):
        day = get_object_or_404(ProcessDay, pk=day_pk)
        request_pk = request.POST.get('request_pk')
        position_id = request.POST.get('position')

        instance = None
        if request_pk:
            # 1. 編集時: 指定された ID で取得
            instance = StaffRequest.objects.filter(pk=request_pk, process_day=day).first()
        elif position_id:
            # 2. 新規追加時: 同一ポジションが既にある場合はそちらを更新対象にする
            instance = StaffRequest.objects.filter(process_day=day, position_id=position_id).first()

        form = StaffRequestForm(request.POST, instance=instance)
        if form.is_valid():
            req = form.save(commit=False)
            req.process_day = day
            req.save()

            response = HttpResponse()
            production_id = day.process.production.id
            response['HX-Redirect'] = reverse('productions:detail', kwargs={'pk': production_id})
            return response

        return render(
            request,
            'productions/unused/staff_request_form.html',
            {'day': day, 'form': form, 'instance': instance},
        )


class ProductionTemplateListView(LoginRequiredMixin, View):
    """工程テンプレートプリセット一覧を JSON で返す API"""

    def get(self, request):
        templates = list(
            ProductionTemplate.objects.filter(is_active=True).values(
                'id', 'name', 'description', 'template_data'
            )
        )
        return JsonResponse(templates, safe=False)


class ProductionListView(LoginRequiredMixin, ListView):
    """公演一覧"""

    model = Production
    template_name = 'productions/production_list.html'
    context_object_name = 'productions'

    def get_queryset(self):
        from django.db.models import F, Max, Min, Prefetch
        from django.db.models.functions import Coalesce

        sound_designer_prefetch = Prefetch(
            'members',
            queryset=ProductionMember.objects.filter(role=ProductionMember.Role.SOUND_DESIGNER)
            .select_related('user', 'user__profile')
            .order_by('created_at'),
            to_attr='sound_designer_list',
        )
        chief_prefetch = Prefetch(
            'members',
            queryset=ProductionMember.objects.filter(role=ProductionMember.Role.CHIEF)
            .select_related('user', 'user__profile')
            .order_by('created_at'),
            to_attr='chief_list',
        )
        return (
            Production.objects.annotate(
                request_unit_min_date=Min('processes__request_units__work_date'),
                legacy_process_min_date=Min('processes__days__date'),
                request_unit_max_date=Max('processes__request_units__work_date'),
                legacy_process_max_date=Max('processes__days__date'),
                process_min_date=Coalesce('request_unit_min_date', 'legacy_process_min_date'),
                process_max_date=Coalesce('request_unit_max_date', 'legacy_process_max_date'),
                effective_start_date=Coalesce('process_min_date', 'start_date'),
            )
            .select_related('created_by', 'created_by__profile')
            .prefetch_related(sound_designer_prefetch, chief_prefetch)
            .order_by(F('effective_start_date').desc(nulls_last=True))
        )


class ProductionCreateView(LoginRequiredMixin, CreateView):
    """公演の新規作成（タイトル・備考・担当者のみ。全ブロックを自動生成して detail へ遷移）"""

    model = Production
    fields = ['title', 'note']
    template_name = 'productions/production_form.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.accounts.models import UserProfile

        active_user_ids = UserProfile.objects.filter(is_active_staff=True).values_list(
            'user_id', flat=True
        )
        ctx['users'] = (
            User.objects.filter(pk__in=active_user_ids)
            .select_related('profile')
            .order_by('profile__order', 'last_name', 'first_name')
        )
        # バリデーションエラー後の再表示時に選択値を保持する
        ctx['selected_sound_designer_id'] = self.request.POST.get('sound_designer_id', '')
        ctx['selected_chief_id'] = self.request.POST.get('chief_id', '')
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        if form.is_valid():
            # 担当者バリデーション（ModelForm の外側フィールドなので個別チェック）
            sound_designer_id = request.POST.get('sound_designer_id', '').strip()
            chief_id = request.POST.get('chief_id', '').strip()
            if not sound_designer_id and not chief_id:
                ctx = self.get_context_data(form=form)
                ctx['member_error'] = (
                    'サウンドデザイナーまたはチーフを少なくとも1人選択してください。'
                )
                return self.render_to_response(ctx)
            return self.form_valid(form)
        return self.form_invalid(form)

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        today_str = timezone.now().strftime('%Y%m%d')
        base_code = f'P-{today_str}'
        count = Production.objects.filter(code__startswith=base_code).count() + 1
        form.instance.code = f'{base_code}-{count:03d}'
        with transaction.atomic():
            response = super().form_valid(form)
            production = self.object
            # 担当者の登録（選択されている場合のみ）
            for role_value, field_name in [
                (ProductionMember.Role.SOUND_DESIGNER, 'sound_designer_id'),
                (ProductionMember.Role.CHIEF, 'chief_id'),
            ]:
                user_id_str = self.request.POST.get(field_name, '').strip()
                if user_id_str:
                    try:
                        ProductionMember.objects.create(
                            production=production,
                            user_id=int(user_id_str),
                            role=role_value,
                        )
                    except (ValueError, TypeError):
                        pass
            # 全ブロックを自動生成（不要なものはユーザーが後で削除）
            for idx, block in enumerate(SETUP_BLOCKS):
                Process.objects.create(
                    production=production,
                    title=block['label'],
                    block_key=block['key'],
                    order=idx,
                )
        return response

    def get_success_url(self):
        return reverse('productions:detail', kwargs={'pk': self.object.pk})


class ProductionEditView(LoginRequiredMixin, View):
    """公演情報の編集（モーダル用）"""

    def get(self, request, pk):
        production = get_object_or_404(Production, pk=pk)
        form = ProductionForm(instance=production)
        return render(
            request,
            'productions/production_edit_form.html',
            {'production': production, 'form': form},
        )

    def post(self, request, pk):
        production = get_object_or_404(Production, pk=pk)
        form = ProductionForm(request.POST, instance=production)
        if form.is_valid():
            form.save()
            response = HttpResponse()
            response['HX-Redirect'] = reverse('productions:list')
            return response
        return render(
            request,
            'productions/production_edit_form.html',
            {
                'production': production,
                'form': form,
                'error_message': 'エラーが発生しました。入力内容を確認してください。',
            },
        )


class ProductionDetailView(LoginRequiredMixin, DetailView):
    """公演詳細・申請画面"""

    model = Production
    template_name = 'productions/production_detail.html'
    context_object_name = 'production'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 工程ブロックを N+1 なしで一括取得
        # days__process_type は互換性のため残す（ブロック概要カードから将来削除予定）
        processes_qs = list(
            self.object.processes.prefetch_related(
                'request_units',
                'request_units__process_type',
                'request_units__staff_requests__position',
                'request_units__vehicle_request__requested_vehicle',
            ).order_by('order')
        )

        # process_min/max_date を注入（actual_start/end_date の追加 DB クエリを防ぐ）
        all_dated = [u for proc in processes_qs for u in proc.request_units.all() if u.work_date]
        dates = [u.work_date for u in all_dated]
        self.object.process_min_date = min(dates) if dates else None
        self.object.process_max_date = max(dates) if dates else None

        context['processes'] = processes_qs  # 旧ブロック概要カード用（互換性のため残す）
        context['process_blocks'] = _build_process_blocks(processes_qs)

        # 担当者一覧（Role.choices 定義順で並べるため Python 側でソート）
        role_order = {role: idx for idx, (role, _) in enumerate(ProductionMember.Role.choices)}
        members_qs = self.object.members.select_related('user', 'user__profile')
        context['members'] = sorted(
            members_qs,
            key=lambda m: (role_order.get(m.role, 99), m.start_date or date.min),
        )
        return context


class ProductionProcessesPartialView(LoginRequiredMixin, View):
    """HTMX 用: processes-section の部分再描画"""

    def get(self, request, pk):
        production = get_object_or_404(Production, pk=pk)
        processes_qs = list(
            production.processes.prefetch_related(
                'request_units',
                'request_units__staff_requests__position',
                'request_units__vehicle_request__requested_vehicle',
            ).order_by('order')
        )
        return render(
            request,
            'productions/partials/processes_section.html',
            {
                'production': production,
                'process_blocks': _build_process_blocks(processes_qs),
            },
        )


class ProductionSetupView(LoginRequiredMixin, View):
    """工程ブロックのセットアップ（日付入力なし・ブロック構成のみ）"""

    # 日付入力が不要なモード
    _NO_DATE_MODES = {'memo', 'sumida_check', 'kizai_standby'}

    def get(self, request, pk):
        production = get_object_or_404(Production, pk=pk)
        block_defs = SETUP_BLOCKS

        # データベースに登録されているプリセットを取得
        presets = list(
            ProductionTemplate.objects.filter(is_active=True).values(
                'id', 'name', 'description', 'template_data'
            )
        )

        return render(
            request,
            'productions/unused/production_setup.html',
            {
                'production': production,
                'block_defs': block_defs,
                'presets': presets,
            },
        )

    def _render_setup_with_restored(self, request, production, instances_json):
        """バリデーションエラー時に送信データを保持したまま setup 画面を再描画する"""
        try:
            restored_instances = json.loads(instances_json)
        except (json.JSONDecodeError, TypeError):
            restored_instances = None

        presets = list(
            ProductionTemplate.objects.filter(is_active=True).values(
                'id', 'name', 'description', 'template_data'
            )
        )

        return render(
            request,
            'productions/unused/production_setup.html',
            {
                'production': production,
                'block_defs': SETUP_BLOCKS,
                'presets': presets,
                'restored_instances': restored_instances,
            },
        )

    def post(self, request, pk):
        production = get_object_or_404(Production, pk=pk)
        instances_json = request.POST.get('instances_json', '[]')

        try:
            instances_data = json.loads(instances_json)

            if not instances_data:
                raise ValueError('工程ブロックが一つも選択されていません。最低一つは必要です。')

            block_defs_map = {b['key']: b for b in SETUP_BLOCKS}

            # バリデーション
            validated = []
            for inst in instances_data:
                b_key = inst.get('block_key')
                block_def = block_defs_map.get(b_key)
                if not block_def:
                    raise ValueError(f'不正なブロックキーが含まれています: {b_key}')

                raw_title = (inst.get('title') or block_def['label']).strip() or '無題ブロック'
                validated.append({'def': block_def, 'title': raw_title, 'key': b_key})

            # 生成実行（全ブロック Process のみ作成・ProcessDay は後でブロック編集から作成）
            with transaction.atomic():
                for idx, item in enumerate(validated):
                    block_def = item['def']
                    unique_title = self._get_unique_title(production, item['title'])
                    Process.objects.create(
                        production=production,
                        title=unique_title,
                        block_key=item['key'],
                        order=idx,
                    )

            cnt = len(validated)
            msg = (
                f'{cnt} 件の工程ブロックを登録しました。'
                '各ブロックをクリックして詳細を入力してください。'
            )
            messages.success(request, msg)
            return redirect('productions:detail', pk=production.pk)

        except ValueError as e:
            messages.error(request, str(e))
            return self._render_setup_with_restored(request, production, instances_json)
        except Exception:
            messages.error(request, '工程の生成中に予期せぬエラーが発生しました。')
            return self._render_setup_with_restored(request, production, instances_json)

    def _get_unique_title(self, production, title):
        """タイトル重複回避ヘルパー"""
        title = (title or '').strip() or '無題ブロック'
        original_title = title
        counter = 2
        while Process.objects.filter(production=production, title=title).exists():
            title = f'{original_title} ({counter})'
            counter += 1
        return title


class ProcessDayEditView(LoginRequiredMixin, View):
    """工程編集モーダル"""

    def get(self, request, pk):
        day = get_object_or_404(ProcessDay, pk=pk)
        form = ProcessDayForm(instance=day)
        return render(
            request,
            'productions/unused/process_day_form.html',
            {'day': day, 'form': form},
        )

    def post(self, request, pk):
        day = get_object_or_404(ProcessDay, pk=pk)
        form = ProcessDayForm(request.POST, instance=day)
        if form.is_valid():
            day = form.save()
            # 保存成功後は表示整合を取るために production detail 画面へリダイレクト
            response = HttpResponse()
            production_id = day.process.production.id
            response['HX-Redirect'] = reverse('productions:detail', kwargs={'pk': production_id})
            return response

        return render(
            request,
            'productions/unused/process_day_form.html',
            {'day': day, 'form': form},
        )


class ProcessDayCreateView(LoginRequiredMixin, View):
    """工程の新規作成（モーダル）"""

    def get(self, request, production_id):
        production = get_object_or_404(Production, pk=production_id)
        initial = {}
        date_str = request.GET.get('date', '')
        if date_str:
            initial['date'] = date_str
        form = ProcessDayForm(initial=initial)
        return render(
            request,
            'productions/unused/process_day_form.html',
            {'production': production, 'form': form, 'is_create': True},
        )

    def post(self, request, production_id):
        production = get_object_or_404(Production, pk=production_id)
        form = ProcessDayForm(request.POST)
        if form.is_valid():
            process, _ = Process.objects.get_or_create(
                production=production, title='基本工程', defaults={'order': 0}
            )
            day = form.save(commit=False)
            day.process = process
            day.order = ProcessDay.objects.filter(process=process, date=day.date).count()
            day.save()
            response = HttpResponse()
            response['HX-Redirect'] = reverse('productions:detail', kwargs={'pk': production.id})
            return response

        return render(
            request,
            'productions/unused/process_day_form.html',
            {'production': production, 'form': form, 'is_create': True},
        )


class VehicleAssignmentListView(AssignmentManagePermissionMixin, LoginRequiredMixin, View):
    """車両手配管理一覧"""

    def get(self, request, pk):
        production = get_object_or_404(Production, pk=pk)
        # 配下の全 VehicleRequest に対して管理レコードを自動生成（初回アクセス時）
        vehicle_requests = VehicleRequest.objects.filter(
            process_day__process__production=production
        ).select_related('process_day__process', 'requested_vehicle')
        for vr in vehicle_requests:
            VehicleAssignment.objects.get_or_create(vehicle_request=vr)

        assignments = (
            VehicleAssignment.objects.filter(
                vehicle_request__process_day__process__production=production
            )
            .select_related(
                'vehicle_request__process_day__process',
                'vehicle_request__process_day__process_type',
                'vehicle_request__requested_vehicle',
                'assigned_vehicle',
            )
            .order_by(
                'vehicle_request__process_day__date',
                'vehicle_request__requested_time',
            )
        )
        return render(
            request,
            'productions/vehicle_assignment_list.html',
            {
                'production': production,
                'assignments': assignments,
            },
        )


class VehicleAssignmentEditView(AssignmentManagePermissionMixin, LoginRequiredMixin, View):
    """車両手配の編集（モーダル用）"""

    def get(self, request, pk):
        vr = get_object_or_404(VehicleRequest, pk=pk)
        assignment, _ = VehicleAssignment.objects.get_or_create(vehicle_request=vr)
        form = VehicleAssignmentForm(instance=assignment)
        return render(
            request,
            'productions/vehicle_assignment_form.html',
            {'vr': vr, 'assignment': assignment, 'form': form},
        )

    def post(self, request, pk):
        vr = get_object_or_404(VehicleRequest, pk=pk)
        assignment, _ = VehicleAssignment.objects.get_or_create(vehicle_request=vr)
        form = VehicleAssignmentForm(request.POST, instance=assignment)
        if form.is_valid():
            form.save()
            response = HttpResponse()
            response['HX-Redirect'] = reverse(
                'productions:vehicle_assignment_list',
                kwargs={'pk': vr.process_day.process.production_id},
            )
            return response
        return render(
            request,
            'productions/vehicle_assignment_form.html',
            {
                'vr': vr,
                'assignment': assignment,
                'form': form,
                'error_message': 'エラーが発生しました。入力内容を確認してください。',
            },
        )


class ProductionMemberEditView(LoginRequiredMixin, View):
    """公演担当者の追加・編集（モーダル用）"""

    def get(self, request, production_pk=None, pk=None):
        if pk:
            member = get_object_or_404(ProductionMember, pk=pk)
            production = member.production
        else:
            production = get_object_or_404(Production, pk=production_pk)
            member = None
        form = ProductionMemberForm(instance=member)
        return render(
            request,
            'productions/production_member_form.html',
            {'production': production, 'member': member, 'form': form},
        )

    def post(self, request, production_pk=None, pk=None):
        if pk:
            member = get_object_or_404(ProductionMember, pk=pk)
            production = member.production
        else:
            production = get_object_or_404(Production, pk=production_pk)
            member = None
        form = ProductionMemberForm(request.POST, instance=member)
        if form.is_valid():
            m = form.save(commit=False)
            if not pk:
                m.production = production
            m.save()
            response = HttpResponse()
            response['HX-Redirect'] = reverse('productions:detail', kwargs={'pk': production.pk})
            return response
        return render(
            request,
            'productions/production_member_form.html',
            {
                'production': production,
                'member': member,
                'form': form,
                'error_message': 'エラーが発生しました。入力内容を確認してください。',
            },
        )


class ProductionMemberDeleteView(LoginRequiredMixin, View):
    """公演担当者の削除"""

    # 申請可能ロール（将来の権限制御で申請できるロールと必ず一致させること）
    APPLICABLE_ROLES = {
        ProductionMember.Role.SOUND_DESIGNER,
        ProductionMember.Role.CHIEF,
    }

    def post(self, request, pk):
        member = get_object_or_404(ProductionMember, pk=pk)
        production_pk = member.production_id

        # 削除後に申請可能担当者が0人になる場合は削除禁止
        if member.role in self.APPLICABLE_ROLES:
            remaining = (
                ProductionMember.objects.filter(
                    production_id=production_pk,
                    role__in=self.APPLICABLE_ROLES,
                )
                .exclude(pk=pk)
                .count()
            )
            if remaining == 0:
                form = ProductionMemberForm(instance=member)
                return render(
                    request,
                    'productions/production_member_form.html',
                    {
                        'member': member,
                        'production': member.production,
                        'form': form,
                        'error_message': (
                            'この担当者を削除すると、申請可能な担当者'
                            '（サウンドデザイナーまたはチーフ）がいなくなるため削除できません。'
                        ),
                    },
                )

        # NOTE: 現在は物理削除。将来 end_date 運用 / 論理削除に移行する場合は
        #       ここを `member.end_date = date.today(); member.save()` 等に変更する。
        member.delete()
        response = HttpResponse()
        response['HX-Redirect'] = reverse('productions:detail', kwargs={'pk': production_pk})
        return response


class ProductionMemberBulkAddView(LoginRequiredMixin, View):
    """公演担当者の一括追加（モーダル用・Alpine.js）"""

    def _get_users_and_roles(self):
        """共通: アクティブユーザーと役割一覧を返す"""
        from apps.accounts.models import UserProfile

        active_user_ids = UserProfile.objects.filter(is_active_staff=True).values_list(
            'user_id', flat=True
        )
        users = (
            User.objects.filter(pk__in=active_user_ids)
            .select_related('profile')
            .order_by('profile__order', 'last_name', 'first_name')
        )
        return users, active_user_ids, ProductionMember.Role.choices

    def get(self, request, production_pk):
        production = get_object_or_404(Production, pk=production_pk)
        users, _, roles = self._get_users_and_roles()
        return render(
            request,
            'productions/production_member_bulk_form.html',
            {'production': production, 'users': users, 'roles': roles},
        )

    def post(self, request, production_pk):
        production = get_object_or_404(Production, pk=production_pk)
        users, active_user_ids, roles = self._get_users_and_roles()
        error_context = {'production': production, 'users': users, 'roles': roles}

        try:
            submitted = json.loads(request.POST.get('members_json', '[]'))
        except json.JSONDecodeError:
            error_context['error_message'] = 'データの形式が不正です。'
            return render(request, 'productions/production_member_bulk_form.html', error_context)

        valid_user_ids = set(active_user_ids)
        valid_roles = {r[0] for r in ProductionMember.Role.choices}
        valid_items = []

        for i, item in enumerate(submitted):
            user_id = item.get('user_id') or ''
            role = item.get('role') or ''
            # 両方空 → 完全空行なので無視
            if not user_id and not role:
                continue
            if not user_id:
                error_context['error_message'] = f'{i + 1} 行目：担当者を選択してください。'
                return render(
                    request, 'productions/production_member_bulk_form.html', error_context
                )
            if not role:
                error_context['error_message'] = f'{i + 1} 行目：役割を選択してください。'
                return render(
                    request, 'productions/production_member_bulk_form.html', error_context
                )
            try:
                user_id_int = int(user_id)
            except (ValueError, TypeError):
                error_context['error_message'] = f'{i + 1} 行目：担当者の値が不正です。'
                return render(
                    request, 'productions/production_member_bulk_form.html', error_context
                )
            if user_id_int not in valid_user_ids:
                error_context['error_message'] = f'{i + 1} 行目：不正な担当者です。'
                return render(
                    request, 'productions/production_member_bulk_form.html', error_context
                )
            if role not in valid_roles:
                error_context['error_message'] = f'{i + 1} 行目：不正な役割です。'
                return render(
                    request, 'productions/production_member_bulk_form.html', error_context
                )
            raw_start = (item.get('start_date') or '').strip() or None
            raw_end = (item.get('end_date') or '').strip() or None
            if raw_start and raw_end and raw_start > raw_end:
                error_context['error_message'] = (
                    f'{i + 1} 行目：担当開始日は終了日より前にしてください。'
                )
                return render(
                    request, 'productions/production_member_bulk_form.html', error_context
                )
            valid_items.append(
                {
                    'user_id': user_id_int,
                    'role': role,
                    'start_date': raw_start,
                    'end_date': raw_end,
                    'note': (item.get('note') or '').strip(),
                }
            )

        if not valid_items:
            error_context['error_message'] = '少なくとも1名の担当者を入力してください。'
            return render(request, 'productions/production_member_bulk_form.html', error_context)

        ProductionMember.objects.bulk_create(
            [
                ProductionMember(
                    production=production,
                    user_id=item['user_id'],
                    role=item['role'],
                    start_date=item['start_date'],
                    end_date=item['end_date'],
                    note=item['note'],
                )
                for item in valid_items
            ]
        )

        response = HttpResponse()
        response['HX-Redirect'] = reverse('productions:detail', kwargs={'pk': production.pk})
        return response


class ProcessBlockEditView(ProcessEditPermissionMixin, LoginRequiredMixin, View):
    """工程ブロック一括編集（ブロック種別ごとに専用フォームを表示）"""

    def get(self, request, process_pk):
        process = get_object_or_404(
            Process.objects.select_related('production').prefetch_related(
                'request_units',
                'request_units__process_type',
                'request_units__staff_requests__position',
                'request_units__vehicle_request__requested_vehicle',
            ),
            pk=process_pk,
        )
        ctx = self._build_context(process)
        return render(request, 'productions/process_block_edit_modal.html', ctx)

    def post(self, request, process_pk):
        process = get_object_or_404(Process.objects.select_related('production'), pk=process_pk)
        block_key = process.block_key

        try:
            with transaction.atomic():
                if block_key == 'sumida_check':
                    self._save_sumida_check(request, process)
                elif block_key == 'kizai_standby':
                    self._save_kizai_standby(request, process)
                else:
                    self._save_single_day_block(request, process)

            response = HttpResponse('<div></div>')
            response['HX-Trigger'] = 'processBlockSaved'
            return response
        except ValueError as e:
            ctx = self._build_context(process)
            ctx['post_data'] = request.POST
            ctx['error_message'] = str(e)
            return render(
                request,
                'productions/process_block_edit_modal.html',
                ctx,
                status=200,
            )

    # ─── コンテキスト構築 ────────────────────────────────────────────

    def _build_context(self, process):
        block_key = process.block_key
        vehicles = Vehicle.objects.filter(is_active=True).order_by('order', 'name')

        position_map = BLOCK_POSITION_MAP.get(block_key, {})
        position_list = [{'slug': slug, 'label': label} for slug, label in position_map.items()]
        if block_key in ('rehearsal_strike', 'theatre_strike'):
            position_list = [p for p in position_list if p['slug'] not in ('loading', 'unloading')]

        request_units = list(
            process.request_units.prefetch_related(
                'staff_requests__position',
                'vehicle_request__requested_vehicle',
            ).order_by('work_date', 'order', 'start_time', 'id')
        )
        if not request_units:
            request_units = []
            for d in process.days.prefetch_related(
                'staff_requests__position',
                'vehicle_requests__requested_vehicle',
            ).order_by('date', 'order'):
                if d.vehicle_requests.exists() or block_key in TRAVEL_BLOCK_KEYS:
                    request_units.append(
                        {
                            'legacy_day': d,
                            'legacy_unit_type': ProcessRequestUnit.UnitType.TRANSPORT,
                            'vehicle_request': d.vehicle_requests.first(),
                            'staff_requests': [],
                        }
                    )
                if d.staff_requests.exists() and block_key not in TRAVEL_BLOCK_KEYS:
                    request_units.append(
                        {
                            'legacy_day': d,
                            'legacy_unit_type': ProcessRequestUnit.UnitType.STAFFING,
                            'vehicle_request': None,
                            'staff_requests': list(d.staff_requests.all()),
                        }
                    )
        request_units_data = []
        existing_staff_helper = None
        for idx, item in enumerate(request_units):
            if isinstance(item, dict):
                legacy_day = item['legacy_day']
                unit = None
                unit_type = item['legacy_unit_type']
                vehicle_request = item['vehicle_request']
                staff_requests = item['staff_requests']
                work_date = legacy_day.date
                start_time = legacy_day.start_time
                end_time = legacy_day.end_time
                note = legacy_day.note
                setup_label = legacy_day.setup_label
            else:
                unit = item
                unit_type = unit.unit_type
                vehicle_request = getattr(unit, 'vehicle_request', None)
                staff_requests = list(unit.staff_requests.all())
                work_date = unit.work_date
                start_time = unit.start_time
                end_time = unit.end_time
                note = unit.note
                setup_label = unit.setup_label

            staff_by_slug = {sr.position.slug: sr for sr in staff_requests}
            request_units_data.append(
                {
                    'id': unit.pk if unit else '',
                    'order': idx,
                    'unit_type': unit_type,
                    'work_date': work_date.isoformat() if work_date else '',
                    'start_time': start_time.strftime('%H:%M') if start_time else '',
                    'end_time': end_time.strftime('%H:%M') if end_time else '',
                    'note': note or '',
                    'setup_label': (
                        (setup_label or 'setup_staff')
                        if unit_type == ProcessRequestUnit.UnitType.STAFFING
                        else ''
                    ),
                    'vehicle': {
                        'requested_vehicle_id': (
                            str(vehicle_request.requested_vehicle_id or '')
                            if vehicle_request
                            else ''
                        ),
                        'request_kind': (
                            vehicle_request.request_kind
                            if vehicle_request
                            else VehicleRequest.RequestKind.LOAD_IN
                        ),
                        'requested_time': (
                            vehicle_request.requested_time.strftime('%H:%M')
                            if vehicle_request and vehicle_request.requested_time
                            else ''
                        ),
                        'arrival_requested_time': (
                            vehicle_request.arrival_requested_time.strftime('%H:%M')
                            if vehicle_request and vehicle_request.arrival_requested_time
                            else ''
                        ),
                        'route_from': vehicle_request.route_from if vehicle_request else '',
                        'route_to': vehicle_request.route_to if vehicle_request else '',
                        'note': vehicle_request.note if vehicle_request else '',
                        'loading_qty': (
                            str(vehicle_request.loading_qty)
                            if vehicle_request and vehicle_request.loading_qty is not None
                            else ''
                        ),
                        'loading_include_self': (
                            vehicle_request.loading_include_self if vehicle_request else True
                        ),
                        'unloading_qty': (
                            str(vehicle_request.unloading_qty)
                            if vehicle_request and vehicle_request.unloading_qty is not None
                            else ''
                        ),
                        'unloading_include_self': (
                            vehicle_request.unloading_include_self if vehicle_request else True
                        ),
                    },
                    'staff_rows': (
                        [
                            {
                                'slug': pos['slug'],
                                'label': pos['label'],
                                'qty': (
                                    str(staff_by_slug[pos['slug']].quantity)
                                    if pos['slug'] in staff_by_slug
                                    else ''
                                ),
                                'include_self': (
                                    staff_by_slug[pos['slug']].include_self
                                    if pos['slug'] in staff_by_slug
                                    else True
                                ),
                            }
                            for pos in position_list
                        ]
                        if unit_type == ProcessRequestUnit.UnitType.STAFFING
                        else []
                    ),
                }
            )
            if not existing_staff_helper:
                existing_staff_helper = staff_by_slug.get('helper')

        return {
            'process': process,
            'production': process.production,
            'block_key': block_key,
            'vehicles': vehicles,
            'request_units_data': request_units_data,
            'position_list': position_list,
            'existing_staff_helper': existing_staff_helper,
            'position_rows': [],  # kizai_standby との互換性のため残す
            'setup_label_choices': ProcessDay.SETUP_LABEL_CHOICES,
            'final_performance_load_out_date': process.final_performance_load_out_date,
            'final_performance_location': process.final_performance_location,
            'show_staff_add_button': block_key not in TRAVEL_BLOCK_KEYS,
        }

    # ─── 保存ロジック ────────────────────────────────────────────────

    def _save_sumida_check(self, request, process):
        sumida = request.POST.get('sumida_required') == '1'
        process.sumida_required = sumida
        process.save(update_fields=['sumida_required'])

    def _save_kizai_standby(self, request, process):
        assistant = request.POST.get('assistant_required') == '1'
        process.assistant_required = assistant
        process.save(update_fields=['assistant_required'])

        if assistant:
            qty_str = request.POST.get('helper_quantity', '1').strip()
            include_self = request.POST.get('helper_include_self') == '1'
            try:
                qty = max(1, int(qty_str))
            except ValueError:
                qty = 1

            from .models import Position

            position = Position.objects.filter(slug='helper').first()
            if not position:
                return

            # ProcessDay がなければ作成
            slug = BLOCK_PROCESS_TYPE_MAP.get('kizai_standby', 'kizai-standby')
            pt = ProcessType.objects.filter(slug=slug).first()
            if not pt:
                pt = ProcessType.objects.filter(slug='kizai-standby').first()
            if not pt:
                return

            day, _ = ProcessDay.objects.get_or_create(
                process=process,
                process_type=pt,
                defaults={'order': 0},
            )
            StaffRequest.objects.update_or_create(
                process_day=day,
                position=position,
                defaults={'quantity': qty, 'include_self': include_self},
            )
        else:
            # 助っ人不要の場合は既存の ProcessDay ごと削除
            process.days.all().delete()

    def _save_single_day_block(self, request, process):
        """single_day モードのブロック（仕込み・バラシ・旅荷積み等）を保存する"""
        block_key = process.block_key
        final_performance_load_out_date = None
        final_performance_location = ''

        # ProcessType 取得
        pt_slug = BLOCK_PROCESS_TYPE_MAP.get(block_key)
        if not pt_slug:
            raise ValueError(f'ブロックキー "{block_key}" に対応する工程タイプが見つかりません。')
        pt = ProcessType.objects.filter(slug=pt_slug).first()
        if not pt:
            raise ValueError(f'工程タイプ "{pt_slug}" がデータベースに存在しません。')
        if block_key == 'travel_unload':
            final_performance_load_out_date_str = request.POST.get(
                'final_performance_load_out_date', ''
            ).strip()
            final_performance_location = request.POST.get('final_performance_location', '').strip()
            if not final_performance_load_out_date_str:
                raise ValueError('最終公演地搬出日を入力してください。')
            if not final_performance_location:
                raise ValueError('最終公演地を入力してください。')
            try:
                final_performance_load_out_date = datetime.strptime(
                    final_performance_load_out_date_str, '%Y-%m-%d'
                ).date()
            except ValueError as exc:
                raise ValueError('最終公演地搬出日の形式が不正です。') from exc
        request_units_raw = request.POST.get('request_units_json', '[]').strip()
        try:
            submitted_units = json.loads(request_units_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError('申請単位データの形式が不正です。') from exc

        valid_units = [
            unit for unit in submitted_units if isinstance(unit, dict) and unit.get('work_date')
        ]
        if not valid_units:
            raise ValueError('申請単位を1件以上入力してください。')

        position_slugs = list(BLOCK_POSITION_MAP.get(block_key, {}).keys())
        position_map = {
            position.slug: position for position in Position.objects.filter(slug__in=position_slugs)
        }

        process.request_units.all().delete()

        for idx, unit_data in enumerate(valid_units):
            unit_type = unit_data.get('unit_type') or ProcessRequestUnit.UnitType.STAFFING
            if unit_type not in ProcessRequestUnit.UnitType.values:
                raise ValueError('申請単位種別の値が不正です。')
            if (
                block_key in TRAVEL_BLOCK_KEYS
                and unit_type != ProcessRequestUnit.UnitType.TRANSPORT
            ):
                raise ValueError('この工程では人員申請を追加できません。')
            work_date_str = (unit_data.get('work_date') or '').strip()
            if not work_date_str:
                raise ValueError('日付を入力してください。')
            try:
                work_date = datetime.strptime(work_date_str, '%Y-%m-%d').date()
            except ValueError as exc:
                raise ValueError('日付の形式が不正です。') from exc

            def parse_time(raw_value):
                raw_value = (raw_value or '').strip()
                if not raw_value:
                    return None
                try:
                    return datetime.strptime(raw_value, '%H:%M').time()
                except ValueError as exc:
                    raise ValueError('時間の形式が不正です。') from exc

            start_time = (
                None
                if unit_type == ProcessRequestUnit.UnitType.TRANSPORT
                else parse_time(unit_data.get('start_time'))
            )
            end_time = (
                None
                if unit_type == ProcessRequestUnit.UnitType.TRANSPORT
                else parse_time(unit_data.get('end_time'))
            )
            setup_label = (
                (unit_data.get('setup_label') or '').strip()
                if block_key == 'theatre_setup'
                and unit_type == ProcessRequestUnit.UnitType.STAFFING
                else ''
            )
            unit_note = (
                (unit_data.get('note') or '').strip()
                if unit_type == ProcessRequestUnit.UnitType.STAFFING
                else ''
            )
            request_unit = ProcessRequestUnit.objects.create(
                process=process,
                process_type=pt,
                unit_type=unit_type,
                order=idx,
                work_date=work_date,
                start_time=start_time,
                end_time=end_time,
                note=unit_note,
                setup_label=setup_label,
            )

            if unit_type == ProcessRequestUnit.UnitType.TRANSPORT:
                vehicle_data = unit_data.get('vehicle') or {}
                requested_vehicle = None
                requested_vehicle_id = (vehicle_data.get('requested_vehicle_id') or '').strip()
                if requested_vehicle_id:
                    try:
                        requested_vehicle = Vehicle.objects.get(pk=int(requested_vehicle_id))
                    except (Vehicle.DoesNotExist, ValueError) as exc:
                        raise ValueError('希望車種の値が不正です。') from exc

                def parse_non_negative_int(raw_value):
                    raw_value = '' if raw_value is None else str(raw_value).strip()
                    if not raw_value:
                        return None
                    try:
                        return max(0, int(raw_value))
                    except ValueError as exc:
                        raise ValueError('人数の形式が不正です。') from exc

                vehicle_requested_time = parse_time(vehicle_data.get('requested_time'))
                arrival_requested_time = parse_time(vehicle_data.get('arrival_requested_time'))
                loading_qty = parse_non_negative_int(vehicle_data.get('loading_qty'))
                unloading_qty = parse_non_negative_int(vehicle_data.get('unloading_qty'))
                VehicleRequest.objects.create(
                    process_day=None,
                    process_request_unit=request_unit,
                    requested_vehicle=requested_vehicle,
                    request_kind=vehicle_data.get('request_kind')
                    or VehicleRequest.RequestKind.LOAD_IN,
                    requested_time=vehicle_requested_time,
                    arrival_requested_time=arrival_requested_time,
                    route_from=(vehicle_data.get('route_from') or '').strip(),
                    route_to=(vehicle_data.get('route_to') or '').strip(),
                    note=(vehicle_data.get('note') or '').strip(),
                    loading_qty=loading_qty,
                    loading_include_self=bool(vehicle_data.get('loading_include_self', False)),
                    unloading_qty=unloading_qty,
                    unloading_include_self=bool(vehicle_data.get('unloading_include_self', False)),
                )
            else:
                for row in unit_data.get('staff_rows') or []:
                    slug = row.get('slug')
                    position = position_map.get(slug)
                    qty_raw = '' if row.get('qty') is None else str(row.get('qty')).strip()
                    if not position or not qty_raw:
                        continue
                    try:
                        qty = max(1, int(qty_raw))
                    except ValueError as exc:
                        raise ValueError('人員数の形式が不正です。') from exc
                    StaffRequest.objects.create(
                        process_day=None,
                        process_request_unit=request_unit,
                        position=position,
                        quantity=qty,
                        include_self=bool(row.get('include_self', False)),
                    )
        if block_key == 'travel_unload':
            update_fields = []
            if process.final_performance_load_out_date != final_performance_load_out_date:
                process.final_performance_load_out_date = final_performance_load_out_date
                update_fields.append('final_performance_load_out_date')
            if process.final_performance_location != final_performance_location:
                process.final_performance_location = final_performance_location
                update_fields.append('final_performance_location')
            if update_fields:
                process.save(update_fields=update_fields)


class ProcessBlockDeleteView(ProcessEditPermissionMixin, LoginRequiredMixin, View):
    """工程ブロックの削除"""

    def post(self, request, process_pk):
        process = get_object_or_404(Process.objects.select_related('production'), pk=process_pk)
        production = process.production
        title = process.title
        process.delete()
        messages.success(request, f'「{title}」を削除しました。')
        return redirect('productions:detail', pk=production.pk)
