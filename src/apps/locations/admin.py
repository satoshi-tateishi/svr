from django.contrib import admin

from apps.locations.models import Location


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ['sort', 'name', 'furigana', 'postal_code', 'address', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'furigana', 'address']
    ordering = ['sort', 'name']
