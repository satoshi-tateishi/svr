from django.contrib import admin

from .models import (
    Position,
    Process,
    ProcessDay,
    ProcessType,
    Production,
    ProductionHoliday,
    ProductionTemplate,
    StaffRequest,
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


class ProcessInline(admin.TabularInline):
    model = Process
    extra = 1


class StaffRequestInline(admin.TabularInline):
    model = StaffRequest
    extra = 1


class VehicleRequestInline(admin.TabularInline):
    model = VehicleRequest
    extra = 1


class ProcessDayInline(admin.TabularInline):
    model = ProcessDay
    extra = 1
    fields = ('process_type', 'date', 'location', 'start_time', 'end_time', 'order')


@admin.register(Production)
class ProductionAdmin(admin.ModelAdmin):
    list_display = ('code', 'title', 'start_date', 'end_date', 'created_by')
    search_fields = ('code', 'title')
    inlines = [ProductionHolidayInline, ProcessInline]


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


@admin.register(ProcessDay)
class ProcessDayAdmin(admin.ModelAdmin):
    list_display = ('date', 'process_type', 'process', 'location', 'start_time', 'order')
    list_filter = ('date', 'process__production', 'process_type')
    inlines = [StaffRequestInline, VehicleRequestInline]
