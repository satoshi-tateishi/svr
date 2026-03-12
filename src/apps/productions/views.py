import json
from datetime import date, datetime
from datetime import time as dt_time

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

from .forms import ProcessDayForm, ProductionMemberForm, StaffRequestForm, VehicleAssignmentForm
from .mixins import (
    AssignmentManagePermissionMixin,
    ProcessEditPermissionMixin,
    RequestEditPermissionMixin,
)
from .models import (
    Position,
    Process,
    ProcessDay,
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


def _build_process_blocks(processes_qs):
    """工程ブロック表示用データ構造を構築する。

    processes_qs は prefetch_related('days__staff_requests__position',
    'days__vehicle_requests__requested_vehicle') 済みであること。

    将来: BLOCK_POSITION_MAP は apps/productions/templates.py にあるが、
    責務としては constants / definitions モジュールへ寄せる余地がある。
    """
    # 循環 import 回避のため local import（将来 constants 化の際に整理）
    from .templates import BLOCK_POSITION_MAP  # noqa: PLC0415

    result = []
    for proc in processes_qs:
        block_key = proc.block_key
        position_map = BLOCK_POSITION_MAP.get(block_key, {})

        # 【拡張性注記】vehicle_requests は "全件" 収集する。
        # 現状の block_edit フォームは1件編集前提（暫定）だが、
        # 将来的に複数車両申請ブロックを追加できるよう、表示層は常にリストで扱う。
        vehicles: list = []
        day_entries = []

        for day in sorted(proc.days.all(), key=lambda d: (d.date or date.max, d.order)):
            staff_by_slug = {sr.position.slug: sr for sr in day.staff_requests.all()}
            staff_rows = [
                {
                    'label': label,
                    'qty': staff_by_slug[slug].quantity,
                    'include_self': staff_by_slug[slug].include_self,
                }
                for slug, label in position_map.items()
                if slug in staff_by_slug
            ]
            day_entries.append(
                {
                    'date': day.date,
                    'standby_time': day.start_time,
                    'staff_rows': staff_rows,
                }
            )
            vehicles.extend(list(day.vehicle_requests.all()))

        # 表示順を安定化: 配車日 → 配車希望時間 → pk
        vehicles.sort(
            key=lambda v: (
                v.effective_date or date.max,
                v.requested_time or dt_time.max,
                v.pk,
            )
        )

        result.append(
            {
                'process': proc,
                'block_key': block_key,
                'days': day_entries,
                # 【暫定】block_edit フォームは vehicle 1件前提。複数件ある場合も全件表示する。
                # 将来: 車両申請専用ブロックが追加されたとき vehicles リスト全件を活用する。
                'vehicles': vehicles,
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
            'productions/staff_request_bulk_form.html',
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
            return render(request, 'productions/staff_request_bulk_form.html', error_context)

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
                return render(request, 'productions/staff_request_bulk_form.html', error_context)

            # ポジションの実在確認
            if pos_id not in valid_position_ids:
                error_context['error_message'] = f'不正なポジションIDです (ID:{pos_id})。'
                return render(request, 'productions/staff_request_bulk_form.html', error_context)

            # 数量チェック
            if qty < 1:
                pos_name = position_map.get(pos_id)
                error_context['error_message'] = f'「{pos_name}」は1名以上で入力してください。'
                return render(request, 'productions/staff_request_bulk_form.html', error_context)

            # 時間帯のパース
            raw_start = (item.get('start_time') or '').strip() or None
            raw_end = (item.get('end_time') or '').strip() or None

            pos_name = position_map.get(pos_id)

            # end_time のみ入力はエラー
            if raw_end and not raw_start:
                error_context['error_message'] = (
                    f'「{pos_name}」：終了時間のみの入力はできません。開始時間も入力してください。'
                )
                return render(request, 'productions/staff_request_bulk_form.html', error_context)

            # start_time > end_time はエラー
            if raw_start and raw_end and raw_start >= raw_end:
                error_context['error_message'] = (
                    f'「{pos_name}」：開始時間は終了時間より前にしてください。'
                )
                return render(request, 'productions/staff_request_bulk_form.html', error_context)

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
            'productions/vehicle_request_bulk_form.html',
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
            return render(request, 'productions/vehicle_request_bulk_form.html', error_context)

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
                return render(request, 'productions/vehicle_request_bulk_form.html', error_context)

            if vehicle_id not in valid_vehicle_ids:
                error_context['error_message'] = f'不正な車両IDです (ID:{vehicle_id})。'
                return render(request, 'productions/vehicle_request_bulk_form.html', error_context)

            # request_kind のバリデーション：未指定は load_in、不正値はエラー
            raw_kind = item.get('request_kind') or VehicleRequest.RequestKind.LOAD_IN
            if raw_kind not in valid_request_kinds:
                error_context['error_message'] = f'申請種別の値が不正です（{raw_kind}）。'
                return render(request, 'productions/vehicle_request_bulk_form.html', error_context)

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
            'productions/staff_request_form.html',
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
            'productions/staff_request_form.html',
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
                process_min_date=Min('processes__days__date'),
                process_max_date=Max('processes__days__date'),
                # ソート用: ProcessDay がある場合はその最小日付、なければ start_date
                effective_start_date=Coalesce('process_min_date', 'start_date'),
            )
            .select_related('created_by', 'created_by__profile')
            .prefetch_related(sound_designer_prefetch, chief_prefetch)
            .order_by(F('effective_start_date').desc(nulls_last=True))
        )


class ProductionCreateView(LoginRequiredMixin, CreateView):
    """公演の新規作成（タイトル・担当者のみ。全ブロックを自動生成して detail へ遷移）"""

    model = Production
    fields = ['title']
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
                'days',
                'days__process_type',
                'days__staff_requests__position',
                'days__vehicle_requests__requested_vehicle',
            ).order_by('order')
        )

        # process_min/max_date を注入（actual_start/end_date の追加 DB クエリを防ぐ）
        all_dated = [d for proc in processes_qs for d in proc.days.all() if d.date]
        dates = [d.date for d in all_dated]
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
                'days',
                'days__staff_requests__position',
                'days__vehicle_requests__requested_vehicle',
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
            'productions/production_setup.html',
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
            'productions/production_setup.html',
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
        return render(request, 'productions/process_day_form.html', {'day': day, 'form': form})

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

        return render(request, 'productions/process_day_form.html', {'day': day, 'form': form})


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
            'productions/process_day_form.html',
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
            'productions/process_day_form.html',
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
                'days',
                'days__process_type',
                'days__staff_requests__position',
                'days__vehicle_requests__requested_vehicle',
            ),
            pk=process_pk,
        )
        ctx = self._build_context(process)
        # HTMX リクエストの場合はモーダル用テンプレートを返す
        if request.headers.get('HX-Request'):
            return render(request, 'productions/process_block_edit_modal.html', ctx)
        return render(request, 'productions/process_block_edit.html', ctx)

    def post(self, request, process_pk):
        process = get_object_or_404(Process.objects.select_related('production'), pk=process_pk)
        block_key = process.block_key
        production = process.production

        try:
            with transaction.atomic():
                if block_key == 'sumida_check':
                    self._save_sumida_check(request, process)
                elif block_key == 'kizai_standby':
                    self._save_kizai_standby(request, process)
                elif block_key in ('memo_1', 'memo_2', 'memo_3'):
                    self._save_memo(request, process)
                else:
                    self._save_single_day_block(request, process)

            # HTMX モーダル内保存成功: modal をクリアし processBlockSaved イベントを発火
            if request.headers.get('HX-Request'):
                response = HttpResponse('<div></div>')
                response['HX-Trigger'] = 'processBlockSaved'
                return response

            messages.success(request, f'「{process.title}」を保存しました。')
            return redirect('productions:detail', pk=production.pk)
        except ValueError as e:
            if request.headers.get('HX-Request'):
                ctx = self._build_context(process)
                ctx['post_data'] = request.POST
                ctx['error_message'] = str(e)
                return render(
                    request,
                    'productions/process_block_edit_modal.html',
                    ctx,
                    status=422,
                )
            messages.error(request, str(e))
            ctx = self._build_context(process)
            ctx['post_data'] = request.POST
            return render(request, 'productions/process_block_edit.html', ctx)

    # ─── コンテキスト構築 ────────────────────────────────────────────

    def _build_context(self, process):
        block_key = process.block_key
        vehicles = Vehicle.objects.filter(is_active=True).order_by('order', 'name')
        days = list(
            process.days.prefetch_related(
                'staff_requests__position',
                'vehicle_requests__requested_vehicle',
            ).order_by('date', 'order')
        )

        position_map = BLOCK_POSITION_MAP.get(block_key, {})
        position_list = [{'slug': slug, 'label': label} for slug, label in position_map.items()]

        days_data = []
        existing_vehicle = None
        existing_staff_helper = None
        for d in days:
            staff_by_slug = {sr.position.slug: sr for sr in d.staff_requests.all()}
            days_data.append(
                {
                    'date': d.date.isoformat() if d.date else '',
                    'standby_time': d.start_time.strftime('%H:%M') if d.start_time else '',
                    'positions': {
                        s: {
                            'qty': staff_by_slug[s].quantity if s in staff_by_slug else '',
                            'include_self': (
                                staff_by_slug[s].include_self if s in staff_by_slug else False
                            ),
                        }
                        for s in position_map
                    },
                }
            )
            if not existing_vehicle:
                existing_vehicle = d.vehicle_requests.first()
            if not existing_staff_helper:
                existing_staff_helper = staff_by_slug.get('helper')

        return {
            'process': process,
            'production': process.production,
            'block_key': block_key,
            'vehicles': vehicles,
            'days_data': days_data,
            'position_list': position_list,
            'existing_vehicle': existing_vehicle,
            'existing_staff_helper': existing_staff_helper,
            'position_rows': [],  # kizai_standby との互換性のため残す
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

    def _save_memo(self, request, process):
        note = request.POST.get('note', '').strip()
        process.note = note
        process.save(update_fields=['note'])

    def _save_single_day_block(self, request, process):
        """single_day モードのブロック（仕込み・バラシ・旅荷積み等）を保存する"""
        block_key = process.block_key

        # ProcessType 取得
        pt_slug = BLOCK_PROCESS_TYPE_MAP.get(block_key)
        if not pt_slug:
            raise ValueError(f'ブロックキー "{block_key}" に対応する工程タイプが見つかりません。')
        pt = ProcessType.objects.filter(slug=pt_slug).first()
        if not pt:
            raise ValueError(f'工程タイプ "{pt_slug}" がデータベースに存在しません。')

        # ── 人員申請（多日 JSON）────────────────────────────────────────
        staff_days_raw = request.POST.get('staff_days_json', '[]').strip()
        try:
            staff_days = json.loads(staff_days_raw)
        except (ValueError, TypeError):
            staff_days = []

        valid_days = [d for d in staff_days if isinstance(d, dict) and d.get('date')]
        if not valid_days:
            raise ValueError('日付を1件以上入力してください。')

        # 全 ProcessDay を削除して再作成（VehicleRequest は後でフォームから再作成する）
        process.days.all().delete()

        first_day = None
        for idx, day_data in enumerate(valid_days):
            try:
                block_date = datetime.strptime(day_data['date'], '%Y-%m-%d').date()
            except (ValueError, KeyError):
                continue

            standby_str = (day_data.get('standby_time') or '').strip()
            standby_time = None
            if standby_str:
                try:
                    standby_time = datetime.strptime(standby_str, '%H:%M').time()
                except ValueError:
                    pass

            pd = ProcessDay.objects.create(
                process=process,
                process_type=pt,
                date=block_date,
                start_time=standby_time,
                order=idx,
            )
            if first_day is None:
                first_day = pd

            positions_data = day_data.get('positions', {})
            for pos_slug, pos_data in positions_data.items():
                qty_raw = pos_data.get('qty', '')
                if qty_raw == '' or qty_raw is None:
                    continue
                try:
                    qty = max(1, int(qty_raw))
                except (ValueError, TypeError):
                    continue
                position = Position.objects.filter(slug=pos_slug).first()
                if not position:
                    continue
                StaffRequest.objects.create(
                    process_day=pd,
                    position=position,
                    quantity=qty,
                    include_self=bool(pos_data.get('include_self', False)),
                )

        if first_day is None:
            raise ValueError('有効な日付が1件もありませんでした。')

        # ── 車両申請 ────────────────────────────────────────────────────
        vehicle_id_str = request.POST.get('vehicle_id', '').strip()
        vehicle = None
        if vehicle_id_str:
            try:
                vehicle = Vehicle.objects.get(pk=int(vehicle_id_str))
            except (Vehicle.DoesNotExist, ValueError):
                pass

        if vehicle:
            req_time_str = request.POST.get('requested_time', '').strip()
            arr_time_str = request.POST.get('arrival_requested_time', '').strip()
            route_from = request.POST.get('route_from', '').strip()
            route_to = request.POST.get('route_to', '').strip()
            req_kind = request.POST.get('request_kind', VehicleRequest.RequestKind.LOAD_IN)
            vehicle_date_str = request.POST.get('vehicle_date', '').strip()
            # 荷役人数（車両申請がある場合のみ保存）
            loading_qty_str = request.POST.get('loading_qty', '').strip()
            unloading_qty_str = request.POST.get('unloading_qty', '').strip()
            loading_include_self = request.POST.get('loading_include_self') == '1'
            unloading_include_self = request.POST.get('unloading_include_self') == '1'

            req_time = arr_time = vehicle_date = None
            loading_qty = unloading_qty = None
            try:
                if req_time_str:
                    req_time = datetime.strptime(req_time_str, '%H:%M').time()
                if arr_time_str:
                    arr_time = datetime.strptime(arr_time_str, '%H:%M').time()
                if vehicle_date_str:
                    vehicle_date = datetime.strptime(vehicle_date_str, '%Y-%m-%d').date()
                if loading_qty_str:
                    loading_qty = max(0, int(loading_qty_str))
                if unloading_qty_str:
                    unloading_qty = max(0, int(unloading_qty_str))
            except ValueError:
                pass

            VehicleRequest.objects.create(
                process_day=first_day,
                requested_vehicle=vehicle,
                request_kind=req_kind,
                date=vehicle_date,
                requested_time=req_time,
                arrival_requested_time=arr_time,
                route_from=route_from,
                route_to=route_to,
                loading_qty=loading_qty,
                loading_include_self=loading_include_self,
                unloading_qty=unloading_qty,
                unloading_include_self=unloading_include_self,
            )

        # 備考をブロック（Process）に保存
        note = request.POST.get('note', '').strip()
        if note != process.note:
            process.note = note
            process.save(update_fields=['note'])


class ProcessBlockDeleteView(ProcessEditPermissionMixin, LoginRequiredMixin, View):
    """工程ブロックの削除"""

    def post(self, request, process_pk):
        process = get_object_or_404(Process.objects.select_related('production'), pk=process_pk)
        production = process.production
        title = process.title
        process.delete()
        messages.success(request, f'「{title}」を削除しました。')
        return redirect('productions:detail', pk=production.pk)
