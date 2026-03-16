import json
from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, View

from apps.performances.models.vehicle import Vehicle
from apps.performances.services.dashboard_query_service import DashboardQueryService

from .forms import (
    ProductionForm,
    ProductionMemberForm,
    VehicleAssignmentAssignForm,
    VehicleAssignmentForm,
)
from .mixins import (
    AssignmentManagePermissionMixin,
    ProcessEditPermissionMixin,
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
            'productions/production_edit_modal.html',
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
            'productions/production_edit_modal.html',
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
            'productions/vehicle_assignment_edit_modal.html',
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
            'productions/vehicle_assignment_edit_modal.html',
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


# 搬出系: 車を現場につける時刻（配車時刻）が主役の申請種別
#   - unloading: 車を現場につけて積み降ろし開始する時刻が重要
#   - loading: 倉庫・積み込み場所に車をつける時刻が重要
#   - pickup: 回収場所に車をつける時刻が重要
# 搬入系 (それ以外: load_in, preload, other): 目的地への到着時刻が主役
#   NOTE: other は暫定で搬入系扱い。request_kind の意味整理時に再確認すること。
_OUTBOUND_KINDS = ['loading', 'unloading', 'pickup']


@login_required(login_url='accounts:login')
def production_vehicle_assignment_dashboard(request):
    """配車手配一覧（確認用）: 日付・手配時間グループで俯瞰する"""
    from itertools import groupby

    from django.db.models import BooleanField, Case, F, TimeField, When
    from django.db.models.functions import Coalesce

    from .services.permissions import can_manage_assignments

    if not can_manage_assignments(request.user):
        return HttpResponseForbidden('手配管理の権限がありません。')

    # VehicleAssignment の自動生成（N+1 を bulk_create で解消）
    all_vr_ids = list(VehicleRequest.objects.values_list('pk', flat=True))
    existing_vr_ids = set(
        VehicleAssignment.objects.filter(vehicle_request_id__in=all_vr_ids).values_list(
            'vehicle_request_id', flat=True
        )
    )
    missing_vr_ids = set(all_vr_ids) - existing_vr_ids
    if missing_vr_ids:
        VehicleAssignment.objects.bulk_create(
            [VehicleAssignment(vehicle_request_id=pk) for pk in missing_vr_ids],
            ignore_conflicts=True,
        )

    # annotate: effective_date / is_outbound / primary_time（申請時間） を DB 計算
    assignments = (
        VehicleAssignment.objects.select_related(
            'vehicle_request__process_day__process__production',
            'vehicle_request__process_day__process_type',
            'vehicle_request__process_request_unit__process__production',
            'vehicle_request__process_request_unit__process_type',
            'vehicle_request__requested_vehicle',
            'assigned_vehicle',
        )
        .annotate(
            effective_date_db=Coalesce(
                'vehicle_request__date',
                'vehicle_request__process_request_unit__work_date',
                'vehicle_request__process_day__date',
            ),
            is_outbound=Case(
                When(vehicle_request__request_kind__in=_OUTBOUND_KINDS, then=True),
                default=False,
                output_field=BooleanField(),
            ),
            primary_time=Case(
                When(
                    vehicle_request__request_kind__in=_OUTBOUND_KINDS,
                    then=F('vehicle_request__requested_time'),
                ),
                default=F('vehicle_request__arrival_requested_time'),
                output_field=TimeField(),
            ),
            # 管理配車時間 > 申請時間 の優先順位でソート。両方 null は最後尾（NULLS LAST）
            effective_sort_time=Coalesce(
                'arranged_departure_time', 'vehicle_request__requested_time'
            ),
        )
        .order_by(
            F('effective_date_db').asc(nulls_last=True),
            F('effective_sort_time').asc(nulls_last=True),
            'vehicle_request__route_to',
            'pk',
        )
    )

    # Python 側で日付 → 手配時間グループに二段グルーピング
    dashboard_days = []
    for date_key, date_group in groupby(list(assignments), key=lambda a: a.effective_date_db):
        items = list(date_group)
        Status = VehicleAssignment.Status

        # 管理配車時間グループ（arranged_departure_time が同じものをまとめる。None は「時間未定」）
        # groupby は連続同一キーのみグループ化するため、事前に arranged_departure_time で再ソート
        import datetime as _dt

        items_for_group = sorted(
            items,
            key=lambda a: (
                a.arranged_departure_time is None,
                a.arranged_departure_time
                if a.arranged_departure_time is not None
                else _dt.time.max,
            ),
        )
        time_groups = []
        for dep_time, tg in groupby(items_for_group, key=lambda a: a.arranged_departure_time):
            time_groups.append({'arranged_departure_time': dep_time, 'items': list(tg)})

        edit_date = date_key.isoformat() if date_key else None
        dashboard_days.append(
            {
                'date': date_key,
                'summary': {
                    'total_count': len(items),
                    'pending_count': sum(1 for a in items if a.status == Status.PENDING),
                    'reviewing_count': sum(1 for a in items if a.status == Status.REVIEWING),
                    'confirmed_count': sum(1 for a in items if a.status == Status.CONFIRMED),
                },
                'time_groups': time_groups,
                'edit_date': edit_date,
            }
        )

    return render(
        request,
        'production_management/production_vehicle_assignment_dashboard.html',
        {'dashboard_days': dashboard_days},
    )


@login_required(login_url='accounts:login')
def production_vehicle_assignment_day_edit(request, date_str):
    """配車手配編集（車両レーン方式）: 未割当タスクを車両レーンに割当てる"""
    import datetime as dt

    from django.db.models import Case, F, TimeField, When
    from django.db.models.functions import Coalesce

    from .services.permissions import can_manage_assignments

    if not can_manage_assignments(request.user):
        return HttpResponseForbidden('手配管理の権限がありません。')

    try:
        target_date = dt.date.fromisoformat(date_str)
    except ValueError:
        return HttpResponseForbidden('日付の形式が不正です。')

    # その日の VehicleRequest に対応する VehicleAssignment を自動生成（初回アクセス対応）
    day_vr_ids = list(
        VehicleRequest.objects.annotate(
            eff_date=Coalesce(
                'date',
                'process_request_unit__work_date',
                'process_day__date',
            )
        )
        .filter(eff_date=target_date)
        .values_list('pk', flat=True)
    )
    if day_vr_ids:
        existing_ids = set(
            VehicleAssignment.objects.filter(vehicle_request_id__in=day_vr_ids).values_list(
                'vehicle_request_id', flat=True
            )
        )
        missing = set(day_vr_ids) - existing_ids
        if missing:
            VehicleAssignment.objects.bulk_create(
                [VehicleAssignment(vehicle_request_id=pk) for pk in missing],
                ignore_conflicts=True,
            )

    # 指定日の VehicleAssignment を全件取得
    assignments_list = list(
        VehicleAssignment.objects.select_related(
            'vehicle_request__process_day__process__production',
            'vehicle_request__process_day__process_type',
            'vehicle_request__process_request_unit__process__production',
            'vehicle_request__process_request_unit__process_type',
            'vehicle_request__requested_vehicle',
            'assigned_vehicle',
        )
        .annotate(
            effective_date_db=Coalesce(
                'vehicle_request__date',
                'vehicle_request__process_request_unit__work_date',
                'vehicle_request__process_day__date',
            ),
            primary_time=Case(
                When(
                    vehicle_request__request_kind__in=_OUTBOUND_KINDS,
                    then=F('vehicle_request__requested_time'),
                ),
                default=F('vehicle_request__arrival_requested_time'),
                output_field=TimeField(),
            ),
        )
        .filter(effective_date_db=target_date)
    )

    # 右ペイン: 配置済み（いずれかの時間が設定済み）
    placed_items = [
        a
        for a in assignments_list
        if a.arranged_departure_time is not None or a.arranged_arrival_time is not None
    ]
    placed_pks = [a.pk for a in placed_items]

    # 左ペイン: 全件を申請時間順（null は末尾）
    all_items = sorted(
        assignments_list,
        key=lambda a: (a.primary_time is None, a.primary_time),
    )

    # 車両リスト・デフォルト車両（新音車）
    vehicles = list(Vehicle.objects.filter(is_active=True).order_by('order', 'name'))
    default_vehicle = Vehicle.objects.filter(name='新音車', is_active=True).first()

    return render(
        request,
        'production_management/production_vehicle_assignment_day_edit.html',
        {
            'target_date': target_date,
            'all_items': all_items,
            'placed_items': placed_items,
            'placed_pks': placed_pks,
            'vehicles': vehicles,
            'default_vehicle_id': default_vehicle.pk if default_vehicle else '',
        },
    )


def _build_vehicle_lanes(assigned_items):
    """
    割当済み VehicleAssignment を (車両順, 便時間順) で構造化する。

    NOTE: trip.arrival_time は便内1件目の arranged_arrival_time を代表値とする。
    同便内で異なる到着時間を持つ可能性があるが、表示上の参考値として許容する。
    """
    import datetime as dt
    from itertools import groupby

    # 1回のソートで「車両順 → 便時間順 → pk順」を確立する
    # groupby は連続した同一キーのみグループ化するため、事前ソートが必須
    sorted_items = sorted(
        assigned_items,
        key=lambda a: (
            a.assigned_vehicle.order if a.assigned_vehicle.order is not None else 9999,
            a.assigned_vehicle.name,
            a.arranged_departure_time is None,  # False が先（時間あり優先）
            a.arranged_departure_time if a.arranged_departure_time is not None else dt.time.max,
            a.pk,
        ),
    )

    lanes = []
    for _vid, vehicle_grp in groupby(sorted_items, key=lambda a: a.assigned_vehicle_id):
        vehicle_items = list(vehicle_grp)
        vehicle_obj = vehicle_items[0].assigned_vehicle

        # 各車両グループ内は既に departure_time 順にソート済み
        trips = []
        for dep_time, trip_grp in groupby(vehicle_items, key=lambda a: a.arranged_departure_time):
            trip_items = list(trip_grp)
            trips.append(
                {
                    'departure_time': dep_time,
                    'arrival_time': trip_items[0].arranged_arrival_time,  # 代表値: 1件目
                    'items': trip_items,
                }
            )

        lanes.append({'vehicle': vehicle_obj, 'trips': trips})

    return lanes


@login_required(login_url='accounts:login')
def production_vehicle_assignment_assign(request, pk):
    """インライン割当フォーム（HTMX: GET=フォーム展開 / POST=保存）"""
    from .services.permissions import can_manage_assignments

    if not can_manage_assignments(request.user):
        return HttpResponseForbidden('手配管理の権限がありません。')

    assignment = get_object_or_404(VehicleAssignment, pk=pk)

    if request.method == 'POST':
        form = VehicleAssignmentAssignForm(request.POST, instance=assignment)
        if form.is_valid():
            form.save()
            response = HttpResponse()
            response['HX-Refresh'] = 'true'
            return response
        return render(
            request,
            'production_management/partials/assignment_inline_form.html',
            {'form': form, 'assignment': assignment},
        )

    form = VehicleAssignmentAssignForm(instance=assignment)
    return render(
        request,
        'production_management/partials/assignment_inline_form.html',
        {'form': form, 'assignment': assignment},
    )


@login_required(login_url='accounts:login')
def production_vehicle_assignment_dnd_assign(request, pk):
    """DnD割当 POST: leg='dep'/'arr' で片方のみ更新可能"""
    from .services.permissions import can_manage_assignments

    if not can_manage_assignments(request.user):
        return HttpResponseForbidden('手配管理の権限がありません。')
    if request.method != 'POST':
        return HttpResponseForbidden()

    assignment = get_object_or_404(VehicleAssignment, pk=pk)
    leg = request.POST.get('leg')

    if leg == 'dep':
        update_fields = []
        time_val = request.POST.get('time')
        if time_val is not None:  # time が送られたときだけ時間を更新
            assignment.arranged_departure_time = time_val or None
            update_fields.append('arranged_departure_time')
        note_val = request.POST.get('note')
        if note_val is not None:  # note が送られたときだけ備考を更新
            assignment.departure_note = note_val
            update_fields.append('departure_note')
        if update_fields:
            assignment.save(update_fields=update_fields)
    elif leg == 'arr':
        update_fields = []
        time_val = request.POST.get('time')
        if time_val is not None:
            assignment.arranged_arrival_time = time_val or None
            update_fields.append('arranged_arrival_time')
        note_val = request.POST.get('note')
        if note_val is not None:
            assignment.arrival_note = note_val
            update_fields.append('arrival_note')
        if update_fields:
            assignment.save(update_fields=update_fields)
    else:
        # 後方互換（旧呼び出し形式）
        vehicle_id = request.POST.get('vehicle_id') or None
        departure = request.POST.get('arranged_departure_time') or None
        arrival = request.POST.get('arranged_arrival_time') or None
        if vehicle_id:
            assignment.assigned_vehicle = get_object_or_404(Vehicle, pk=vehicle_id, is_active=True)
        else:
            assignment.assigned_vehicle = None
        assignment.arranged_departure_time = departure
        assignment.arranged_arrival_time = arrival
        assignment.save(
            update_fields=['assigned_vehicle', 'arranged_departure_time', 'arranged_arrival_time']
        )

    return HttpResponse(status=200)


@login_required(login_url='accounts:login')
def production_vehicle_assignment_dnd_remove(request, pk):
    """DnD削除: leg='dep'/'arr' で片方のみクリア、未指定は両方クリア"""
    from .services.permissions import can_manage_assignments

    if not can_manage_assignments(request.user):
        return HttpResponseForbidden('手配管理の権限がありません。')
    if request.method != 'POST':
        return HttpResponseForbidden()

    assignment = get_object_or_404(VehicleAssignment, pk=pk)

    # leg 未指定: 時間・備考・車両を全てクリア（割当解除）
    assignment.assigned_vehicle = None
    assignment.arranged_departure_time = None
    assignment.arranged_arrival_time = None
    assignment.departure_note = ''
    assignment.arrival_note = ''
    assignment.save(
        update_fields=[
            'assigned_vehicle',
            'arranged_departure_time',
            'arranged_arrival_time',
            'departure_note',
            'arrival_note',
        ]
    )

    return HttpResponse(status=200)


@login_required(login_url='accounts:login')
def production_vehicle_assignment_assign_cancel(request, pk):
    """割当フォームキャンセル（HTMX: 元のボタン状態に戻す）"""
    from .services.permissions import can_manage_assignments

    if not can_manage_assignments(request.user):
        return HttpResponseForbidden('手配管理の権限がありません。')

    assignment = get_object_or_404(VehicleAssignment, pk=pk)
    return render(
        request,
        'production_management/partials/assign_button.html',
        {'assignment': assignment},
    )
