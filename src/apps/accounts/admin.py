from django import forms
from django.contrib import admin
from django.utils.html import format_html

from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile


# ============================================================
# 標準 User モデルのカスタマイズ
# ============================================================

admin.site.unregister(User)


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    """
    標準の UserAdmin をオーバーライドして項目順序を日本式に変更する。
    """

    # 一覧画面の順序: メールアドレス -> 氏名
    list_display = ('email', 'display_name', 'is_staff', 'is_active')
    list_display_links = ('email', 'display_name')
    ordering = ('email',)

    @admin.display(description='氏名', ordering='last_name')
    def display_name(self, obj):
        return f'{obj.last_name} {obj.first_name}'.strip() or obj.username

    # 編集画面の順序: 姓 -> 名
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (
            '個人情報',
            {
                'fields': (
                    'last_name',
                    'first_name',
                    'email',
                )
            },
        ),
        (
            '権限',
            {
                'fields': (
                    'is_active',
                    'is_staff',
                    'is_superuser',
                    'groups',
                    'user_permissions',
                ),
            },
        ),
        ('重要な日付', {'fields': ('last_login', 'date_joined')}),
    )


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
            'is_active_staff',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['is_active'].initial = self.instance.user.is_active


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    form = UserProfileAdminForm
    list_display = (
        'order',
        'display_full_name',
        'is_active_staff',
    )
    list_editable = ('order', 'is_active_staff')
    list_display_links = ('display_full_name',)
    list_filter = ('system_role', 'user__is_active')
    search_fields = ('user__username', 'family_name', 'given_name', 'email')
    
    @admin.display(description='氏名', ordering='family_name')
    def display_full_name(self, obj):
        return obj.full_name
    fieldsets = (
        (
            '基本情報',
            {
                'description': (
                    'テストデータ作成のため、全フィールドを編集可能にしています。'
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
                'fields': (
                    'system_role',
                    'order',
                    'is_active_staff',
                ),
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
        return True

    def has_delete_permission(self, request, obj=None):
        return True

    def get_readonly_fields(self, request, obj=None):
        return ()

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
