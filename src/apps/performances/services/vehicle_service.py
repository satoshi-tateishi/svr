"""
VehicleService — 車輌マスタ・運行工程サービス
"""

from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.performances.models.base import Performance
from apps.performances.models.vehicle import Vehicle, VehicleOperation


class VehicleService:
    @staticmethod
    def create_vehicle(
        name: str,
        vehicle_type: str,
        ownership_type: str,
        note: str = '',
    ) -> Vehicle:
        """車輌マスタに車輌を登録する"""
        return Vehicle.objects.create(
            name=name,
            vehicle_type=vehicle_type,
            ownership_type=ownership_type,
            note=note,
        )

    @staticmethod
    @transaction.atomic
    def create_operation(
        performance: Performance,
        title: str,
        requested_start: datetime,
        requested_end: datetime,
        route_from: str,
        route_to: str,
        description: str = '',
    ) -> VehicleOperation:
        """
        運行工程を作成する（希望時間として登録）。

        Args:
            requested_start/end: 制作の希望時間（確定後も上書きしない）

        Raises:
            ValidationError: 希望終了が希望開始より前の場合
        """
        if requested_end <= requested_start:
            raise ValidationError('希望終了時刻は希望開始時刻より後に設定してください。')

        return VehicleOperation.objects.create(
            performance=performance,
            title=title,
            requested_start=requested_start,
            requested_end=requested_end,
            route_from=route_from,
            route_to=route_to,
            description=description,
        )

    @staticmethod
    @transaction.atomic
    def confirm_schedule(
        operation: VehicleOperation,
        scheduled_start: datetime,
        scheduled_end: datetime,
    ) -> VehicleOperation:
        """
        運行工程の確定時間を設定する。

        requested_* は変更しない（乖離の証跡として保持）。

        Raises:
            ValidationError: 確定済み（Locked）の工程を変更しようとした場合
        """
        if operation.status == VehicleOperation.Status.LOCKED:
            raise ValidationError('確定済みの運行工程は変更できません。')

        if scheduled_end <= scheduled_start:
            raise ValidationError('確定終了時刻は確定開始時刻より後に設定してください。')

        operation.scheduled_start = scheduled_start
        operation.scheduled_end = scheduled_end
        operation.status = VehicleOperation.Status.ASSIGNED
        operation.save(update_fields=['scheduled_start', 'scheduled_end', 'status', 'updated_at'])
        return operation
