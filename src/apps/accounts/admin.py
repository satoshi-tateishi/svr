from django import forms
from django.contrib import admin
from django.utils.html import format_html

from .models import UserProfile


class UserProfileAdminForm(forms.ModelForm):
    is_active = forms.BooleanField(
        label='アカウント有効',
        required=False,
        help_text='無効にするとログインできなくなります。削除の代わりにこのフラグで管理してください。',
    )

    class Meta:
        model = UserProfile
        fields = (
            'system_role',
            'portal_uuid',
            'family_name',
            'given_name',
            'phonetic_family_name',
            'phonetic_given_name',
            'phone_number',
            'email',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['is_active'].initial = self.instance.user.is_active


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    form = UserProfileAdminForm
    list_display = (
        'get_portal_uuid',
        'full_name',
        'system_role',
        'phone_number',
        'email',
        'get_is_active',
    )
    list_filter = ('system_role', 'user__is_active')
    search_fields = ('user__username', 'family_name', 'given_name', 'email')
    fieldsets = (
        (
            '基本情報（Portal 同期）',
            {
                'description': (
                    'Portal 同期情報は shin•on Portal JWT から自動同期されます。'
                    'このアプリからは編集できません。'
                ),
                'fields': (
                    ('family_name', 'given_name'),
                    ('phonetic_family_name', 'phonetic_given_name'),
                    'portal_uuid',
                    'email',
                    'phone_number',
                    'is_active',
                ),
            },
        ),
        (
            'svr 設定',
            {
                'fields': ('system_role',),
            },
        ),
    )

    # JWT で同期されるフィールド（system_role・is_active は除く）
    _JWT_SYNC_FIELDS = (
        'portal_uuid',
        'family_name',
        'given_name',
        'phonetic_family_name',
        'phonetic_given_name',
        'phone_number',
        'email',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return self._JWT_SYNC_FIELDS

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.user.is_active = form.cleaned_data.get('is_active', True)
        obj.user.save(update_fields=['is_active'])

    @admin.display(description='ポータルUUID', ordering='user__username')
    def get_portal_uuid(self, obj):
        return obj.portal_uuid or format_html('<span style="color: #999;">未連携</span>')

    @admin.display(description='有効', boolean=True, ordering='user__is_active')
    def get_is_active(self, obj):
        return obj.user.is_active
