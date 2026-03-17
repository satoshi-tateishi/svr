from django.contrib import admin

from .models import (
    Position,
    Process,
    ProcessDay,
    ProcessType,
    Production,
    ProductionHoliday,
    ProductionMember,
    ProductionTemplate,
    StaffRequest,
    VehicleAssignment,
    VehicleRequest,
)


@admin.register(ProductionTemplate)
class ProductionTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'updated_at')
    list_editable = ('is_active',)
    search_fields = ('name', 'description')
    ordering = ('name',)


class ProductionHolidayInline(admin.TabularInline):
    model = ProductionHoliday
    extra = 1


class ProductionMemberInline(admin.TabularInline):
    model = ProductionMember
    extra = 1
    fields = ('user', 'role', 'start_date', 'end_date', 'note')


class ProcessInline(admin.TabularInline):
    model = Process
    extra = 1


class StaffRequestInline(admin.TabularInline):
    model = StaffRequest
    extra = 1


class VehicleRequestInline(admin.TabularInline):
    model = VehicleRequest
    extra = 1
    fields = (
        'requested_vehicle',
        'request_kind',
        'requested_time',
        'arrival_requested_time',
        'route_from',
        'location_from',
        'from_address',
        'route_to',
        'location_to',
        'to_address',
        'note',
    )
    readonly_fields = ('from_address', 'to_address')

    @admin.display(description='出発地 住所')
    def from_address(self, obj):
        return obj.location_from.address if obj.location_from else '-'

    @admin.display(description='目的地 住所')
    def to_address(self, obj):
        return obj.location_to.address if obj.location_to else '-'


class ProcessDayInline(admin.TabularInline):
    model = ProcessDay
    extra = 1
    fields = ('process_type', 'date', 'location', 'start_time', 'end_time', 'order')


@admin.register(Production)
class ProductionAdmin(admin.ModelAdmin):
    list_display = ('code', 'title', 'start_date', 'end_date', 'created_by')
    search_fields = ('code', 'title')
    inlines = [ProductionMemberInline, ProductionHolidayInline, ProcessInline]


@admin.register(ProductionMember)
class ProductionMemberAdmin(admin.ModelAdmin):
    list_display = ('production', 'role', 'user', 'start_date', 'end_date')
    list_filter = ('role',)
    search_fields = ('production__title', 'user__last_name', 'user__first_name')


@admin.register(ProcessType)
class ProcessTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'color', 'order', 'is_active')
    list_editable = ('color', 'order', 'is_active')


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'order')
    list_editable = ('order',)


@admin.register(Process)
class ProcessAdmin(admin.ModelAdmin):
    list_display = ('production', 'title', 'order')
    list_filter = ('production',)
    inlines = [ProcessDayInline]


class VehicleAssignmentInline(admin.StackedInline):
    model = VehicleAssignment
    extra = 0
    fields = ('status', 'assigned_vehicle', 'note')


@admin.register(ProcessDay)
class ProcessDayAdmin(admin.ModelAdmin):
    list_display = ('date', 'process_type', 'process', 'location', 'start_time', 'order')
    list_filter = ('date', 'process__production', 'process_type')
    inlines = [StaffRequestInline, VehicleRequestInline]


@admin.register(VehicleAssignment)
class VehicleAssignmentAdmin(admin.ModelAdmin):
    list_display = ('vehicle_request', 'status', 'assigned_vehicle', 'updated_at')
    list_filter = ('status',)
    search_fields = ('vehicle_request__process_day__process__production__title',)
