from itertools import groupby
from datetime import datetime, timedelta
import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.generic import DetailView, ListView, View, CreateView
from django.urls import reverse
from django.utils import timezone
from django.db import transaction

from .forms import ProcessDayForm
from .models import ProcessDay, Production, Process, ProcessType, ProductionTemplate
from .templates import PRODUCTION_TEMPLATES, LOCATION_GROUPS


class ProductionTemplateListView(LoginRequiredMixin, View):
    """工程テンプレートプリセット一覧を JSON で返す API"""
    def get(self, request):
        templates = list(ProductionTemplate.objects.filter(is_active=True).values(
            "id", "name", "description", "template_data"
        ))
        return JsonResponse(templates, safe=False)


class ProductionListView(LoginRequiredMixin, ListView):

    """公演一覧"""
    model = Production
    template_name = "productions/production_list.html"
    context_object_name = "productions"
    ordering = ["-start_date"]


class ProductionCreateView(LoginRequiredMixin, CreateView):
    """公演の新規作成"""
    model = Production
    fields = ["title", "start_date", "end_date", "note"]
    template_name = "productions/production_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        today_str = timezone.now().strftime('%Y%m%d')
        base_code = f"P-{today_str}"
        count = Production.objects.filter(code__startswith=base_code).count() + 1
        form.instance.code = f"{base_code}-{count:03d}"
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("productions:setup", kwargs={"pk": self.object.pk})


class ProductionDetailView(LoginRequiredMixin, DetailView):
    """公演詳細・申請画面"""
    model = Production
    template_name = "productions/production_detail.html"
    context_object_name = "production"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        process_days = ProcessDay.objects.filter(
            process__production=self.object
        ).select_related(
            'process', 'process_type'
        ).prefetch_related(
            'staff_requests', 
            'staff_requests__position', 
            'vehicle_requests'
        ).order_by("date", "order", "start_time")

        grouped_days = []
        for date, group in groupby(process_days, key=lambda x: x.date):
            grouped_days.append({
                "date": date,
                "days": list(group)
            })
            
        context["grouped_days"] = grouped_days
        return context


class ProductionSetupView(LoginRequiredMixin, View):
    """テンプレートからの工程セットアップ"""

    def get(self, request, pk):
        production = get_object_or_404(Production, pk=pk)
        template_key = request.GET.get("template", "standard")
        template = PRODUCTION_TEMPLATES.get(template_key, PRODUCTION_TEMPLATES["standard"])
        
        location_slots = self._build_location_slots()
        
        # データベースに登録されているプリセットを取得
        presets = list(ProductionTemplate.objects.filter(is_active=True).values(
            "id", "name", "description", "template_data"
        ))
        
        return render(request, "productions/production_setup.html", {
            "production": production,
            "template": template,
            "template_key": template_key,
            "template_blocks": template["blocks"],
            "location_slots": location_slots,
            "templates_all": PRODUCTION_TEMPLATES,
            "presets": presets,
        })

    def _build_location_slots(self):
        """ロケーションスロットの組み立てヘルパー"""
        location_slots = []
        for group_key, group_def in LOCATION_GROUPS.items():
            slots = [{"id": f"{group_key}_{i}", "label": f"{group_def['label']}{i+1}"} 
                     for i in range(group_def["default_slots"])]
            location_slots.append({
                "group_key": group_key,
                "label": group_def["label"],
                "slots": slots
            })
        return location_slots

    def post(self, request, pk):
        production = get_object_or_404(Production, pk=pk)
        
        try:
            # 1. JSON ペイロードの取得とパース
            instances_json = request.POST.get("instances_json", "[]")
            locations_json = request.POST.get("locations_json", "{}")
            instances_data = json.loads(instances_json)
            locations_data = json.loads(locations_json)
            
            if not instances_data:
                raise ValueError("工程ブロックが一つも選択されていません。最低一つは必要です。")

            # 2. テンプレート定義のロード
            template_key = request.POST.get("template_key", "standard")
            template = PRODUCTION_TEMPLATES.get(template_key, PRODUCTION_TEMPLATES["standard"])
            block_defs = {b["key"]: b for b in template["blocks"]}

            # 3. 事前バリデーション
            required_slugs = set()
            validated_instances = []
            
            for idx, inst in enumerate(instances_data):
                t_key = inst.get("template_key")
                block_def = block_defs.get(t_key)
                if not block_def:
                    raise ValueError(f"不正なテンプレートキーが含まれています: {t_key}")

                # タイトル取得（トリミングは _get_unique_title 内でも行うがここでもチェック）
                raw_title = (inst.get("title") or block_def["label"]).strip()
                if not raw_title:
                    raw_title = "無題ブロック"

                # 日付の存在チェック
                s_val = inst.get("start")
                e_val = inst.get("end")
                if not s_val:
                    raise ValueError(f"ブロック「{raw_title}」の開始日が未入力です。")
                
                is_range = block_def.get("mode") not in ["single_day", "manual_subtasks"]
                if is_range and not e_val:
                    raise ValueError(f"ブロック「{raw_title}」の終了日が未入力です。")

                try:
                    start_date = datetime.strptime(s_val, "%Y-%m-%d").date()
                    end_date = datetime.strptime(e_val, "%Y-%m-%d").date() if is_range else start_date
                except ValueError:
                    raise ValueError(f"ブロック「{raw_title}」の日付形式が不正です。")

                if end_date < start_date:
                    raise ValueError(f"ブロック「{raw_title}」の終了日が開始日より前になっています。")

                # ProcessType チェック対象の収集
                if block_def.get("mode") != "manual_subtasks":
                    tasks = block_def.get("tasks", [])
                    required_slugs.update(tasks)
                    if block_def.get("mode") == "date_range_performance":
                        required_slugs.add("opening-night")

                validated_instances.append({
                    "def": block_def,
                    "title": raw_title,
                    "start_date": start_date,
                    "end_date": end_date,
                    "location_choice": inst.get("location_choice"),
                })

            # 4. ProcessType の一括存在確認
            pt_map = {pt.slug: pt for pt in ProcessType.objects.filter(slug__in=required_slugs)}
            missing_slugs = required_slugs - set(pt_map.keys())
            if missing_slugs:
                raise ValueError(f"システムエラー: 以下の工程タイプが未定義です: {', '.join(sorted(missing_slugs))}")

            # 5. 生成実行 (トランザクション)
            with transaction.atomic():
                for idx, item in enumerate(validated_instances):
                    block_def = item["def"]
                    unique_title = self._get_unique_title(production, item["title"])
                    
                    process = Process.objects.create(
                        production=production,
                        title=unique_title,
                        order=idx
                    )

                    if block_def.get("mode") == "manual_subtasks":
                        continue

                    location_name = locations_data.get(item["location_choice"], "")
                    self._create_process_days(process, block_def, item["start_date"], item["end_date"], location_name, pt_map)

            messages.success(request, f"{len(validated_instances)} 件の工程を正常に生成しました。")
            return redirect("productions:detail", pk=production.pk)

        except ValueError as e:
            messages.error(request, str(e))
            return redirect("productions:setup", pk=pk)
        except Exception:
            messages.error(request, "工程の生成中に予期せぬエラーが発生しました。入力内容を確認してください。")
            return redirect("productions:setup", pk=pk)

    def _get_unique_title(self, production, title):
        """タイトル重複回避ヘルパー"""
        title = (title or "").strip()
        if not title:
            title = "無題ブロック"
        
        original_title = title
        counter = 2
        while Process.objects.filter(production=production, title=title).exists():
            title = f"{original_title} ({counter})"
            counter += 1
        return title

    def _create_process_days(self, process, block_def, start_date, end_date, location_name, pt_map):
        """ProcessDay 群を生成する内部ロジック"""
        mode = block_def.get("mode", "single_day")
        curr_date = start_date
        day_offset = 0
        
        while curr_date <= end_date:
            for task_idx, task_slug in enumerate(block_def["tasks"]):
                final_slug = task_slug
                if mode == "date_range_performance" and day_offset == 0:
                    final_slug = "opening-night"

                pt = pt_map[final_slug]
                ProcessDay.objects.create(
                    process=process,
                    process_type=pt,
                    date=curr_date,
                    location=location_name,
                    order=task_idx,
                )
            
            if mode == "single_day":
                break
            curr_date += timedelta(days=1)
            day_offset += 1


class ProcessDayEditView(LoginRequiredMixin, View):
    """工程編集モーダル"""
    def get(self, request, pk):
        day = get_object_or_404(ProcessDay, pk=pk)
        form = ProcessDayForm(instance=day)
        return render(request, "productions/process_day_form.html", {
            "day": day,
            "form": form
        })

    def post(self, request, pk):
        day = get_object_or_404(ProcessDay, pk=pk)
        form = ProcessDayForm(request.POST, instance=day)
        if form.is_valid():
            day = form.save()
            # 保存成功後は表示整合を取るために production detail 画面へリダイレクト
            response = HttpResponse()
            response["HX-Redirect"] = reverse("productions:detail", kwargs={"pk": day.process.production.id})
            return response
        
        return render(request, "productions/process_day_form.html", {
            "day": day,
            "form": form
        })


class ProcessDayCreateView(LoginRequiredMixin, View):
    """工程の新規作成（モーダル）"""
    def get(self, request, production_id):
        production = get_object_or_404(Production, pk=production_id)
        form = ProcessDayForm()
        return render(request, "productions/process_day_form.html", {
            "production": production,
            "form": form,
            "is_create": True
        })

    def post(self, request, production_id):
        production = get_object_or_404(Production, pk=production_id)
        form = ProcessDayForm(request.POST)
        if form.is_valid():
            # TODO: 申請ユーザー向け画面では "基本工程" 以外の適切なブロック選択が必要
            process, _ = Process.objects.get_or_create(
                production=production,
                title="基本工程",
                defaults={"order": 0}
            )
            day = form.save(commit=False)
            day.process = process
            day.save()
            response = HttpResponse()
            response["HX-Redirect"] = reverse("productions:detail", kwargs={"pk": production.id})
            return response
        
        return render(request, "productions/process_day_form.html", {
            "production": production,
            "form": form,
            "is_create": True
        })
