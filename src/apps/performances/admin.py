from django.contrib import admin

from .models import (
    Performance,
    PerformanceFreelanceRate,
    PerformancePosition,
    PerformanceResponsibleStaff,
    Phase,
    PhaseSlot,
    StaffAssignment,
    Vehicle,
    VehicleAssignment,
    VehicleOperation,
)

# ============================================================
# インライン定義
# ============================================================


class PhaseSlotInline(admin.TabularInline):
    model = PhaseSlot
    extra = 0
    fields = ('requested_staff_count', 'status')
    readonly_fields = ('status',)


class PhaseInline(admin.TabularInline):
    model = Phase
    extra = 0
    fields = ('order', 'name', 'suggested_date')
    ordering = ('order',)


class StaffAssignmentInline(admin.TabularInline):
    model = StaffAssignment
    extra = 0
    fields = ('user', 'position', 'occupied_start', 'occupied_end')

    def get_readonly_fields(self, request, obj=None):
        # Lock 済みはスナップショットフィールドも表示（読み取り専用）
        if obj and obj.status == PhaseSlot.Status.LOCKED:
            return (
                'user',
                'position',
                'occupied_start',
                'occupied_end',
                'applied_unit_price',
                'applied_total_amount',
                'locked_at',
            )
        return ()


class VehicleAssignmentInline(admin.TabularInline):
    model = VehicleAssignment
    extra = 0
    fields = ('vehicle', 'driver_user', 'is_external_driver')


class PerformanceResponsibleStaffInline(admin.TabularInline):
    model = PerformanceResponsibleStaff
    extra = 1
    fields = ('user', 'position')


class FreelanceRateInline(admin.TabularInline):
    model = PerformanceFreelanceRate
    extra = 0
    fields = ('user', 'position', 'unit_price', 'allowance', 'valid_from', 'valid_until')
    # 単価は上書き禁止なので既存行はすべて読み取り専用
    readonly_fields = ('user', 'position', 'unit_price', 'allowance', 'valid_from', 'valid_until')

    def has_delete_permission(self, request, obj=None):
        return False


# ============================================================
# 公演（Performance）
# ============================================================


@admin.register(Performance)
class PerformanceAdmin(admin.ModelAdmin):
    list_display = ('title', 'display_start_date', 'display_end_date', 'created_by', 'has_phases', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('title',)
    readonly_fields = ('created_by', 'created_at', 'updated_at')
    inlines = [PhaseInline, PerformanceResponsibleStaffInline, FreelanceRateInline]

    @admin.display(description='開始日')
    def display_start_date(self, obj):
        return obj.start_date

    @admin.display(description='終了日')
    def display_end_date(self, obj):
        return obj.end_date

    @admin.display(description='工程展開済', boolean=True)
    def has_phases(self, obj):
        return obj.has_phases

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# ============================================================
# ポジションマスタ（PerformancePosition）
# ============================================================


@admin.register(PerformancePosition)
class PerformancePositionAdmin(admin.ModelAdmin):
    list_display = ('name', 'order')
    list_editable = ('order',)
    ordering = ('order', 'name')


# ============================================================
# 工程（Phase）
# ============================================================


@admin.register(Phase)
class PhaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'performance', 'order', 'suggested_date')
    list_filter = ('performance',)
    inlines = [PhaseSlotInline]


# ============================================================
# 車輌マスタ（Vehicle）
# ============================================================


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('name', 'vehicle_type', 'ownership_type', 'is_active')
    list_filter = ('vehicle_type', 'ownership_type', 'is_active')
    search_fields = ('name',)


# ============================================================
# 運行工程（VehicleOperation）
# ============================================================


@admin.register(VehicleOperation)
class VehicleOperationAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'performance',
        'requested_start',
        'scheduled_start',
        'status',
        'drift_display',
    )
    list_filter = ('status', 'performance')
    readonly_fields = ('status',)
    inlines = [VehicleAssignmentInline]

    @admin.display(description='乖離（分）')
    def drift_display(self, obj):
        drift = obj.schedule_drift_minutes
        if drift is None:
            return '—（未確定）'
        if abs(drift) > 30:
            return f'⚠ {drift:+d} 分'
        return f'{drift:+d} 分'
