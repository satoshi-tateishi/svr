"""
ReportService — PDF 帳票生成サービス（Week 6 最重要）

【設計原則】
- Lock 済みデータ（status == LOCKED、applied_* フィールド確定済み）からのみ生成可能。
- 未 Lock データを混在させない（Lock 制約の徹底）。
- WeasyPrint（HTML/CSS → PDF）でレイアウトを HTML テンプレートに分離する。
- 生成した PDF はバイト列で返し、呼び出し元（View）が HttpResponse に詰める。

【帳票種別】
1. 公演手配書（performance_report）: 現場スタッフ・ドライバー配布用。金額非表示。
2. 手配実績証明書（financial_report）: 経理提出・PDF 保存用。applied_* フィールドを全表示。
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils import timezone

from apps.performances.models.base import Performance, PhaseSlot
from apps.performances.models.staff import StaffAssignment
from apps.performances.models.vehicle import VehicleAssignment, VehicleOperation


class ReportService:
    @staticmethod
    def _get_locked_staff_data(performance: Performance) -> list[dict]:
        """
        Lock 済み人員割当データを帳票用辞書リストに変換して返す。

        Returns:
            [
                {
                    'phase_name': '1. 機材作り',
                    'suggested_start_date': date(2026, 6, 1),
                    'assignments': [
                        {
                            'staff_name': '山田太郎',
                            'position_name': '照明',
                            'occupied_start': datetime,
                            'occupied_end': datetime,
                            'applied_unit_price': 15000,
                            'applied_allowance_total': 500,
                            'applied_total_amount': 15500,
                        },
                        ...
                    ],
                },
                ...
            ]
        """
        locked_slots = (
            PhaseSlot.objects.filter(
                phase__performance=performance,
                status=PhaseSlot.Status.LOCKED,
            )
            .select_related('phase')
            .order_by('phase__order')
        )

        result = []
        for slot in locked_slots:
            assignments = (
                StaffAssignment.objects.filter(phase_slot=slot)
                .select_related('user', 'position')
                .filter(locked_at__isnull=False)
                .order_by('occupied_start')
            )

            assignment_data = []
            for a in assignments:
                assignment_data.append(
                    {
                        'staff_name': a.user.get_full_name() or a.user.username,
                        'position_name': a.applied_position_name or '（未設定）',
                        'occupied_start': a.occupied_start,
                        'occupied_end': a.occupied_end,
                        'applied_unit_price': a.applied_unit_price or 0,
                        'applied_allowance_total': a.applied_allowance_total or 0,
                        'applied_total_amount': a.applied_total_amount or 0,
                    }
                )

            result.append(
                {
                    'phase_name': slot.phase.name,
                    'suggested_start_date': slot.phase.suggested_start_date,
                    'suggested_end_date': slot.phase.suggested_end_date,
                    'assignments': assignment_data,
                }
            )

        return result

    @staticmethod
    def _get_locked_vehicle_data(performance: Performance) -> list[dict]:
        """
        Lock 済み配車割当データを帳票用辞書リストに変換して返す。

        Returns:
            [
                {
                    'title': '劇場搬入',
                    'route_from': '倉庫',
                    'route_to': '劇場',
                    'scheduled_start': datetime,
                    'scheduled_end': datetime,
                    'assignments': [
                        {
                            'vehicle_name': '2tトラックA',
                            'vehicle_type': '2tトラック',
                            'driver_name': '佐藤次郎',
                            'is_external_driver': False,
                            'applied_cost_amount': 25000,
                        },
                        ...
                    ],
                },
                ...
            ]
        """
        locked_operations = VehicleOperation.objects.filter(
            performance=performance,
            status=VehicleOperation.Status.LOCKED,
        ).order_by('scheduled_start', 'requested_start')

        result = []
        for op in locked_operations:
            assignments = (
                VehicleAssignment.objects.filter(vehicle_operation=op)
                .select_related('vehicle', 'driver_user')
                .filter(locked_at__isnull=False)
            )

            assignment_data = []
            for a in assignments:
                driver_name = ''
                if a.driver_user:
                    driver_name = a.driver_user.get_full_name() or a.driver_user.username
                elif a.is_external_driver:
                    driver_name = '（外注ドライバー）'

                assignment_data.append(
                    {
                        'vehicle_name': a.vehicle.name,
                        'vehicle_type': a.vehicle.get_vehicle_type_display(),
                        'driver_name': driver_name,
                        'is_external_driver': a.is_external_driver,
                        'applied_cost_amount': a.applied_cost_amount or 0,
                    }
                )

            result.append(
                {
                    'title': op.title,
                    'route_from': op.route_from,
                    'route_to': op.route_to,
                    'scheduled_start': op.scheduled_start,
                    'scheduled_end': op.scheduled_end,
                    'assignments': assignment_data,
                }
            )

        return result

    @staticmethod
    def generate_performance_report(performance: Performance) -> bytes:
        """
        公演手配書（現場スタッフ・ドライバー配布用）を PDF バイト列として生成する。

        Lock 済みの人員枠・運行工程のみを含める。金額（applied_*）は非表示。
        Lock 済みデータが一切ない場合は ValidationError を raise する。

        Args:
            performance: PDF 生成対象の公演

        Returns:
            PDF バイト列（HttpResponse に直接詰められる形式）

        Raises:
            ValidationError: Lock 済みデータが存在しない場合
        """
        from weasyprint import HTML

        staff_data = ReportService._get_locked_staff_data(performance)
        vehicle_data = ReportService._get_locked_vehicle_data(performance)

        if not staff_data and not vehicle_data:
            raise ValidationError(
                'Lock 済みの手配データが存在しません。'
                '人員枠または運行工程を確定（Lock）してから帳票を出力してください。'
            )

        context = {
            'performance': performance,
            'staff_data': staff_data,
            'vehicle_data': vehicle_data,
            'generated_at': timezone.now(),
        }

        html_string = render_to_string('performances/reports/performance_report.html', context)
        pdf_bytes = HTML(string=html_string).write_pdf()
        return pdf_bytes

    @staticmethod
    def generate_financial_report(performance: Performance) -> bytes:
        """
        手配実績証明書（経理提出・PDF 保存用）を PDF バイト列として生成する。

        Lock 済みのスナップショット（applied_* フィールド）から金額を集計して出力する。
        設計原則: SaaS 連携と同様、applied_* で始まるスナップショット項目のみを参照する。

        Args:
            performance: PDF 生成対象の公演

        Returns:
            PDF バイト列（HttpResponse に直接詰められる形式）

        Raises:
            ValidationError: Lock 済みデータが存在しない場合
        """
        from weasyprint import HTML

        staff_data = ReportService._get_locked_staff_data(performance)
        vehicle_data = ReportService._get_locked_vehicle_data(performance)

        if not staff_data and not vehicle_data:
            raise ValidationError(
                'Lock 済みの実績データが存在しません。'
                '人員枠または運行工程を確定（Lock）してから帳票を出力してください。'
            )

        # 金額合計の集計（applied_* フィールドのみ使用）
        total_staff_cost = sum(
            a['applied_total_amount'] for phase in staff_data for a in phase['assignments']
        )
        total_vehicle_cost = sum(
            a['applied_cost_amount'] for op in vehicle_data for a in op['assignments']
        )
        grand_total = total_staff_cost + total_vehicle_cost

        context = {
            'performance': performance,
            'staff_data': staff_data,
            'vehicle_data': vehicle_data,
            'total_staff_cost': total_staff_cost,
            'total_vehicle_cost': total_vehicle_cost,
            'grand_total': grand_total,
            'generated_at': timezone.now(),
        }

        html_string = render_to_string('performances/reports/financial_report.html', context)
        pdf_bytes = HTML(string=html_string).write_pdf()
        return pdf_bytes
