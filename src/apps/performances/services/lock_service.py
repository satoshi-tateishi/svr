"""
LockService — スナップショット確定サービス（Week 5 最重要）

【設計原則】
- Lock は不可逆操作。一度 Locked になった Slot/Operation は解除できない。
- 修正が必要な場合は「調整用レコード」を新規作成する（Lock 解除 API は存在しない）。
- @transaction.atomic + select_for_update() で並行 Lock を防ぐ。
- SaaS 連携など外部参照は applied_* フィールドのみを使用すること。
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.performances.exceptions import ZeroCostWarning
from apps.performances.models.base import PhaseSlot
from apps.performances.models.staff import StaffAssignment
from apps.performances.models.vehicle import VehicleAssignment, VehicleOperation
from apps.performances.services.freelance_rate_service import FreelanceRateService


class LockService:
    @staticmethod
    @transaction.atomic
    def lock_phase_slot(slot: PhaseSlot) -> PhaseSlot:
        """
        PhaseSlot を Locked に遷移し、紐付く全 StaffAssignment に単価スナップショットを保存する。

        処理順序:
        1. select_for_update() で PhaseSlot を行ロック取得
        2. 各 StaffAssignment に FreelanceRateService で取得した単価を applied_* に保存
        3. PhaseSlot.status = LOCKED に遷移

        Args:
            slot: 確定対象の人員枠（PhaseSlot）

        Returns:
            status が LOCKED に更新された PhaseSlot

        Raises:
            ValidationError: 対象 Slot が既に Locked 済みの場合
        """
        # 行ロック取得（並行 Lock を防ぐ）
        slot = PhaseSlot.objects.select_for_update().get(pk=slot.pk)

        if slot.status == PhaseSlot.Status.LOCKED:
            raise ValidationError('既に確定済みの人員枠です。')

        now = timezone.now()
        lock_date = now.date()
        performance = slot.phase.performance

        # 紐付く StaffAssignment を行ロック取得
        assignments = list(StaffAssignment.objects.select_for_update().filter(phase_slot=slot))

        for assignment in assignments:
            # ポジションが設定されている場合のみ単価を取得
            if assignment.position:
                rate = FreelanceRateService.get_applicable_rate(
                    user=assignment.user,
                    performance=performance,
                    position=assignment.position,
                    target_date=lock_date,
                )
                if rate:
                    assignment.applied_unit_price = rate.unit_price
                    assignment.applied_allowance_total = rate.allowance
                    assignment.applied_total_amount = rate.unit_price + rate.allowance
                else:
                    # 単価未登録の場合は 0 円でスナップショット
                    assignment.applied_unit_price = 0
                    assignment.applied_allowance_total = 0
                    assignment.applied_total_amount = 0
                assignment.applied_position_name = assignment.position.name
            else:
                # ポジション未設定の場合は 0 円でスナップショット
                assignment.applied_unit_price = 0
                assignment.applied_allowance_total = 0
                assignment.applied_total_amount = 0
                assignment.applied_position_name = ''

            assignment.locked_at = now
            assignment.save(
                update_fields=[
                    'applied_unit_price',
                    'applied_allowance_total',
                    'applied_total_amount',
                    'applied_position_name',
                    'locked_at',
                ]
            )

        slot.status = PhaseSlot.Status.LOCKED
        slot.save(update_fields=['status', 'updated_at'])
        return slot

    @staticmethod
    @transaction.atomic
    def lock_vehicle_operation(
        operation: VehicleOperation, force: bool = False
    ) -> VehicleOperation:
        """
        VehicleOperation を Locked に遷移し、全 VehicleAssignment に原価スナップショットを保存する。

        外注車輌（Vehicle.is_external == True）で applied_cost_amount が 0 円の場合、
        force=False（デフォルト）だと ZeroCostWarning を raise して管理者に確認を促す。
        管理者が意図的に 0 円で確定する場合は force=True を指定して再実行する。

        処理順序:
        1. select_for_update() で VehicleOperation を行ロック取得
        2. force=False の場合、外注車輌の原価 0 円チェック
        3. 各 VehicleAssignment の applied_cost_amount / applied_sales_amount を確定保存
        4. VehicleOperation.status = LOCKED に遷移

        Args:
            operation: 確定対象の運行工程（VehicleOperation）
            force:     外注原価 0 円の警告をスキップして強制確定するか（デフォルト: False）

        Returns:
            status が LOCKED に更新された VehicleOperation

        Raises:
            ValidationError: 対象 Operation が既に Locked 済みの場合
            ZeroCostWarning: 外注車輌の applied_cost_amount が 0 円で force=False の場合
        """
        # 行ロック取得（並行 Lock を防ぐ）
        operation = VehicleOperation.objects.select_for_update().get(pk=operation.pk)

        if operation.status == VehicleOperation.Status.LOCKED:
            raise ValidationError('既に確定済みの運行工程です。')

        # 紐付く VehicleAssignment を行ロック取得
        assignments = list(
            VehicleAssignment.objects.select_for_update()
            .select_related('vehicle')
            .filter(vehicle_operation=operation)
        )

        # 外注原価 0 円の警告チェック（force=True でスキップ可能）
        if not force:
            for assignment in assignments:
                if assignment.vehicle.is_external:
                    cost = assignment.applied_cost_amount
                    if cost is None or cost == 0:
                        raise ZeroCostWarning(
                            f'車輌「{assignment.vehicle.name}」の外注原価が 0 円です。'
                            '確定してよろしいですか？'
                            ' force=True を指定して再実行すると 0 円で確定できます。'
                        )

        now = timezone.now()

        for assignment in assignments:
            # applied_cost_amount が未設定（None）の場合は 0 で確定
            if assignment.applied_cost_amount is None:
                assignment.applied_cost_amount = 0
            assignment.locked_at = now
            assignment.save(update_fields=['applied_cost_amount', 'locked_at'])

        operation.status = VehicleOperation.Status.LOCKED
        operation.save(update_fields=['status', 'updated_at'])
        return operation
