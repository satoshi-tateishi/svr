import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Performance
from .services.performance_service import PerformanceService
from .services.phase_service import PhaseService
from .services.report_service import ReportService

logger = logging.getLogger(__name__)


@login_required(login_url='accounts:login')
def performance_list(request):
    """公演一覧"""
    performances = PerformanceService.get_performance_list(request.user)
    return render(request, 'performances/list.html', {'performances': performances})


@login_required(login_url='accounts:login')
def performance_create(request):
    """公演作成"""
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        start_date = request.POST.get('start_date', '')
        end_date = request.POST.get('end_date', '')

        if not title or not start_date or not end_date:
            return render(
                request,
                'performances/create.html',
                {'error': 'タイトル・開始日・終了日はすべて必須です。'},
            )

        try:
            from datetime import date

            performance = PerformanceService.create_performance(
                title=title,
                start_date=date.fromisoformat(start_date),
                end_date=date.fromisoformat(end_date),
                created_by=request.user,
                description=request.POST.get('description', ''),
            )
            return redirect('performances:detail', pk=performance.pk)
        except Exception as e:
            return render(request, 'performances/create.html', {'error': str(e)})

    return render(request, 'performances/create.html')


@login_required(login_url='accounts:login')
def performance_detail(request, pk):
    """公演詳細（工程・配車一覧）"""
    performance = get_object_or_404(Performance, pk=pk)
    phases = PhaseService.get_phases_with_slots(performance)
    return render(
        request,
        'performances/detail.html',
        {'performance': performance, 'phases': phases},
    )


@login_required(login_url='accounts:login')
@require_POST
def apply_template(request, pk):
    """テンプレート展開（POST のみ受け付ける）"""
    performance = get_object_or_404(Performance, pk=pk)

    start_date_str = request.POST.get('start_date', '')
    if not start_date_str:
        return HttpResponseBadRequest('基準日が指定されていません。')

    try:
        from datetime import date

        start_date = date.fromisoformat(start_date_str)
        PhaseService.apply_production_template(performance, start_date)
        logger.info(
            f'テンプレート展開完了: performance_id={performance.pk}, '
            f'start_date={start_date}, user={request.user.email}'
        )
    except Exception as e:
        logger.warning(f'テンプレート展開失敗: {e}')
        return render(
            request,
            'performances/detail.html',
            {
                'performance': performance,
                'phases': [],
                'error': str(e),
            },
        )

    return redirect('performances:detail', pk=performance.pk)


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
