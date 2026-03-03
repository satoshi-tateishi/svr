"""
AssignmentService — 人員・車輌の紐付けとダブルブッキング防止

【Week 3 最重要サービス】
select_for_update() によるトランザクション制御のもと、
占有時間の重複を検知してダブルブッキングを物理的に遮断する。

外注車輌（Vehicle.ownership_type == 'external'）は
複数工程への割当が前提のため、重複チェックから除外する。
"""

from datetime import datetime

from django.contrib.auth.models import User
from django.db import transaction

from apps.performances.exceptions import ConflictError
from apps.performances.models.base import PerformancePosition, PhaseSlot
from apps.performances.models.staff import StaffAssignment
from apps.performances.models.vehicle import Vehicle, VehicleAssignment, VehicleOperation


class AssignmentService:
    @staticmethod
    @transaction.atomic
    def confirm_staff_assignment(
        slot: PhaseSlot,
        user: User,
        occupied_start: datetime,
        occupied_end: datetime,
        position: PerformancePosition | None = None,
    ) -> StaffAssignment:
        """
        人員割当を確定し、占有時間が重複する場合は ConflictError を raise する。

        select_for_update() でロックを取得してから重複チェックを行うことで、
        並行リクエスト（競合状態）によるダブルブッキングを防ぐ。

        Args:
            slot:           割当先の人員枠（PhaseSlot）
            user:           割り当てるスタッフ
            occupied_start: 占有開始時刻（集合時間）
            occupied_end:   占有終了時刻（解散時間）
            position:       ポジション（省略可）

        Returns:
            作成した StaffAssignment

        Raises:
            ConflictError: 対象スタッフの占有時間が既存割当と重複する場合
        """
        # 並行アクセス対策: 対象スタッフの全割当レコードを行ロック取得
        conflicting = StaffAssignment.objects.select_for_update().filter(
            user=user,
            occupied_start__lt=occupied_end,
            occupied_end__gt=occupied_start,
        )
        if conflicting.exists():
            conflict = conflicting.first()
            raise ConflictError(
                f'{user.get_full_name() or user.username} は '
                f'{conflict.occupied_start}〜{conflict.occupied_end} に既に割当があります。'
            )

        return StaffAssignment.objects.create(
            phase_slot=slot,
            user=user,
            position=position,
            occupied_start=occupied_start,
            occupied_end=occupied_end,
        )

    @staticmethod
    @transaction.atomic
    def confirm_vehicle_assignment(
        operation: VehicleOperation,
        vehicle: Vehicle,
        driver_user: User | None = None,
        is_external_driver: bool = False,
    ) -> VehicleAssignment:
        """
        配車割当を確定し、確定時間が重複する場合は ConflictError を raise する。

        外注車輌（ownership_type == 'external'）は複数工程への割当が業務上許容されるため、
        重複チェックから除外する。

        VehicleOperation の scheduled_start/end が未設定の場合は、
        確定時間が確定していないため重複チェックをスキップする。

        Args:
            operation:         割当先の運行工程（VehicleOperation）
            vehicle:           割り当てる車輌
            driver_user:       ドライバー（省略可）
            is_external_driver: 外注ドライバーフラグ

        Returns:
            作成した VehicleAssignment

        Raises:
            ConflictError: 対象車輌の確定時間が既存割当と重複する場合（外注車輌は除外）
        """
        # 外注車輌は重複チェックから除外（複数工程に割当可能）
        if not vehicle.is_external:
            # 確定時間が設定されている場合のみ重複チェックを実施
            if operation.scheduled_start is not None and operation.scheduled_end is not None:
                # 並行アクセス対策: 対象車輌の全割当レコードを行ロック取得
                conflicting = (
                    VehicleAssignment.objects.select_for_update()
                    .filter(
                        vehicle=vehicle,
                        vehicle_operation__scheduled_start__isnull=False,
                        vehicle_operation__scheduled_end__isnull=False,
                        vehicle_operation__scheduled_start__lt=operation.scheduled_end,
                        vehicle_operation__scheduled_end__gt=operation.scheduled_start,
                    )
                    .exclude(vehicle_operation=operation)
                )
                if conflicting.exists():
                    conflict = conflicting.first()
                    raise ConflictError(
                        f'車輌「{vehicle.name}」は '
                        f'{conflict.vehicle_operation.scheduled_start}'
                        f'〜{conflict.vehicle_operation.scheduled_end} '
                        f'に既に割当があります。'
                    )

        return VehicleAssignment.objects.create(
            vehicle_operation=operation,
            vehicle=vehicle,
            driver_user=driver_user,
            is_external_driver=is_external_driver,
        )
