import json
from datetime import date, datetime, timedelta
from itertools import groupby

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
from .mixins import AssignmentManagePermissionMixin, RequestEditPermissionMixin
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
from .templates import LOCATION_GROUPS, PRODUCTION_TEMPLATES


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
    """公演の新規作成"""

    model = Production
    fields = ['title', 'start_date', 'end_date', 'note']
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
            # 担当者の自動生成（選択されている場合のみ）
            production = self.object
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
                        pass  # 不正な値は無視（通常は発生しない）
        return response

    def get_success_url(self):
        return reverse('productions:setup', kwargs={'pk': self.object.pk})


class ProductionDetailView(LoginRequiredMixin, DetailView):
    """公演詳細・申請画面"""

    model = Production
    template_name = 'productions/production_detail.html'
    context_object_name = 'production'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # process_days をリスト化して1回のクエリで評価
        process_days_list = list(
            ProcessDay.objects.filter(process__production=self.object)
            .select_related('process', 'process_type')
            .prefetch_related(
                'staff_requests',
                'staff_requests__position',
                'vehicle_requests',
                'vehicle_requests__requested_vehicle',
            )
            .order_by('date', 'order', 'start_time')
        )

        # ProcessDay の min/max を production に注入（actual_start/end_date の DB クエリを防ぐ）
        dates = [d.date for d in process_days_list]
        self.object.process_min_date = min(dates) if dates else None
        self.object.process_max_date = max(dates) if dates else None

        grouped_days = []
        for day_date, group in groupby(process_days_list, key=lambda x: x.date):
            grouped_days.append({'date': day_date, 'days': list(group)})

        context['grouped_days'] = grouped_days

        # 担当者一覧（Role.choices 定義順で並べるため Python 側でソート）
        role_order = {role: idx for idx, (role, _) in enumerate(ProductionMember.Role.choices)}
        members_qs = self.object.members.select_related('user', 'user__profile')
        context['members'] = sorted(
            members_qs,
            key=lambda m: (role_order.get(m.role, 99), m.start_date or date.min),
        )
        return context


class ProductionSetupView(LoginRequiredMixin, View):
    """テンプレートからの工程セットアップ"""

    def get(self, request, pk):
        production = get_object_or_404(Production, pk=pk)
        template_key = request.GET.get('template', 'standard')
        template = PRODUCTION_TEMPLATES.get(template_key, PRODUCTION_TEMPLATES['standard'])

        location_slots = self._build_location_slots()

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
                'template': template,
                'template_key': template_key,
                'template_blocks': template['blocks'],
                'location_slots': location_slots,
                'templates_all': PRODUCTION_TEMPLATES,
                'presets': presets,
            },
        )

    def _build_location_slots(self):
        """ロケーションスロットの組み立てヘルパー"""
        location_slots = []
        for group_key, group_def in LOCATION_GROUPS.items():
            slots = [
                {'id': f'{group_key}_{i}', 'label': f'{group_def["label"]}{i + 1}'}
                for i in range(group_def['default_slots'])
            ]
            location_slots.append(
                {'group_key': group_key, 'label': group_def['label'], 'slots': slots}
            )
        return location_slots

    def _render_setup_with_restored(self, request, production, instances_json, locations_json):
        """バリデーションエラー時に送信データを保持したまま setup 画面を再描画する"""
        template_key = request.POST.get('template_key', 'standard')
        template = PRODUCTION_TEMPLATES.get(template_key, PRODUCTION_TEMPLATES['standard'])
        location_slots = self._build_location_slots()
        presets = list(
            ProductionTemplate.objects.filter(is_active=True).values(
                'id', 'name', 'description', 'template_data'
            )
        )
        try:
            restored_instances = json.loads(instances_json)
        except (json.JSONDecodeError, TypeError):
            restored_instances = None

        try:
            restored_locations = json.loads(locations_json)
        except (json.JSONDecodeError, TypeError):
            restored_locations = None

        return render(
            request,
            'productions/production_setup.html',
            {
                'production': production,
                'template': template,
                'template_key': template_key,
                'template_blocks': template['blocks'],
                'location_slots': location_slots,
                'templates_all': PRODUCTION_TEMPLATES,
                'presets': presets,
                'restored_instances': restored_instances,
                'restored_locations': restored_locations,
            },
        )

    def post(self, request, pk):
        production = get_object_or_404(Production, pk=pk)
        instances_json = request.POST.get('instances_json', '[]')
        locations_json = request.POST.get('locations_json', '{}')

        try:
            # 1. JSON ペイロードのパース
            instances_data = json.loads(instances_json)
            locations_data = json.loads(locations_json)

            if not instances_data:
                raise ValueError('工程ブロックが一つも選択されていません。最低一つは必要です。')

            # 2. テンプレート定義のロード
            template_key = request.POST.get('template_key', 'standard')
            template = PRODUCTION_TEMPLATES.get(template_key, PRODUCTION_TEMPLATES['standard'])
            block_defs = {b['key']: b for b in template['blocks']}

            # 3. 事前バリデーション
            required_slugs = set()
            validated_instances = []

            for inst in instances_data:
                t_key = inst.get('template_key')
                block_def = block_defs.get(t_key)
                if not block_def:
                    raise ValueError(f'不正なテンプレートキーが含まれています: {t_key}')

                # タイトル取得（トリミングは _get_unique_title 内でも行うがここでもチェック）
                raw_title = (inst.get('title') or block_def['label']).strip()
                if not raw_title:
                    raw_title = '無題ブロック'

                # 日付の存在チェック
                s_val = inst.get('start')
                e_val = inst.get('end')
                if not s_val:
                    raise ValueError(f'ブロック「{raw_title}」の開始日が未入力です。')

                is_range = block_def.get('mode') not in ['single_day', 'manual_subtasks']
                # 終了日が空の場合は開始日と同日の単日工程として扱う

                try:
                    start_date = datetime.strptime(s_val, '%Y-%m-%d').date()
                    end_date = (
                        datetime.strptime(e_val, '%Y-%m-%d').date()
                        if (is_range and e_val)
                        else start_date
                    )
                except ValueError:
                    raise ValueError(f'ブロック「{raw_title}」の日付形式が不正です。') from None

                if end_date < start_date:
                    raise ValueError(f'ブロック「{raw_title}」の終了日が開始日より前です。')

                # ProcessType チェック対象の収集
                if block_def.get('mode') != 'manual_subtasks':
                    tasks = block_def.get('tasks', [])
                    required_slugs.update(tasks)
                    if block_def.get('mode') == 'date_range_performance':
                        required_slugs.add('opening-night')

                validated_instances.append(
                    {
                        'def': block_def,
                        'title': raw_title,
                        'start_date': start_date,
                        'end_date': end_date,
                        'location_choice': inst.get('location_choice'),
                    }
                )

            # 4. ProcessType の一括存在確認
            pt_map = {pt.slug: pt for pt in ProcessType.objects.filter(slug__in=required_slugs)}
            missing_slugs = required_slugs - set(pt_map.keys())
            if missing_slugs:
                slugs_str = ', '.join(sorted(missing_slugs))
                raise ValueError(f'システムエラー: 以下の工程タイプが未定義です: {slugs_str}')

            # 5. 生成実行 (トランザクション)
            with transaction.atomic():
                for idx, item in enumerate(validated_instances):
                    block_def = item['def']
                    unique_title = self._get_unique_title(production, item['title'])

                    process = Process.objects.create(
                        production=production, title=unique_title, order=idx
                    )

                    if block_def.get('mode') == 'manual_subtasks':
                        continue

                    location_name = locations_data.get(item['location_choice'], '')
                    self._create_process_days(
                        process,
                        block_def,
                        item['start_date'],
                        item['end_date'],
                        location_name,
                        pt_map,
                    )

            messages.success(request, f'{len(validated_instances)} 件の工程を正常に生成しました。')
            return redirect('productions:detail', pk=production.pk)

        except ValueError as e:
            messages.error(request, str(e))
            return self._render_setup_with_restored(
                request, production, instances_json, locations_json
            )
        except Exception:
            messages.error(request, '工程の生成中に予期せぬエラーが発生しました。')
            return self._render_setup_with_restored(
                request, production, instances_json, locations_json
            )

    def _get_unique_title(self, production, title):
        """タイトル重複回避ヘルパー"""
        title = (title or '').strip()
        if not title:
            title = '無題ブロック'

        original_title = title
        counter = 2
        while Process.objects.filter(production=production, title=title).exists():
            title = f'{original_title} ({counter})'
            counter += 1
        return title

    def _create_process_days(self, process, block_def, start_date, end_date, location_name, pt_map):
        """ProcessDay 群を生成する内部ロジック"""
        mode = block_def.get('mode', 'single_day')
        curr_date = start_date
        day_offset = 0

        while curr_date <= end_date:
            for task_idx, task_slug in enumerate(block_def['tasks']):
                final_slug = task_slug
                if mode == 'date_range_performance' and day_offset == 0:
                    final_slug = 'opening-night'

                pt = pt_map[final_slug]
                ProcessDay.objects.create(
                    process=process,
                    process_type=pt,
                    date=curr_date,
                    location=location_name,
                    order=task_idx,
                )

            if mode == 'single_day':
                break
            curr_date += timedelta(days=1)
            day_offset += 1


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
        form = ProcessDayForm()
        return render(
            request,
            'productions/process_day_form.html',
            {'production': production, 'form': form, 'is_create': True},
        )

    def post(self, request, production_id):
        production = get_object_or_404(Production, pk=production_id)
        form = ProcessDayForm(request.POST)
        if form.is_valid():
            # TODO: 申請ユーザー向け画面では "基本工程" 以外の適切なブロック選択が必要
            process, _ = Process.objects.get_or_create(
                production=production, title='基本工程', defaults={'order': 0}
            )
            day = form.save(commit=False)
            day.process = process
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
