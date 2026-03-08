from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    """ユーザー追加情報（ポータル連携・表示制御）"""

    class SystemRole(models.TextChoices):
        ADMIN = 'admin', '管理者'
        EDITOR = 'editor', '編集者'
        GENERAL = 'general', '一般'
        VIEWER = 'viewer', '閲覧者'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    # システム全体のロール
    system_role = models.CharField(
        max_length=20,
        choices=SystemRole.choices,
        default=SystemRole.GENERAL,
        verbose_name='システムロール',
    )

    # ポータル連携用UUID（UUIDFieldに変更）
    portal_uuid = models.UUIDField(
        unique=True, null=True, blank=True, db_index=True, verbose_name='ポータルUUID'
    )

    # 基本プロフィール情報
    family_name = models.CharField(max_length=100, blank=True, default='', verbose_name='姓')
    given_name = models.CharField(max_length=100, blank=True, default='', verbose_name='名')
    phonetic_family_name = models.CharField(
        max_length=100, blank=True, default='', verbose_name='姓(ふりがな)'
    )
    phonetic_given_name = models.CharField(
        max_length=100, blank=True, default='', verbose_name='名(ふりがな)'
    )

    phone_number = models.CharField(max_length=20, blank=True, default='', verbose_name='電話番号')
    email = models.EmailField(blank=True, default='', verbose_name='メールアドレス')

    # 表示順
    order = models.PositiveIntegerField(default=0, verbose_name='表示順')

    # スタッフ選択時の表示フラグ（旧 is_staff をリネーム想定）
    is_active_staff = models.BooleanField(default=True, verbose_name='担当者選択に表示')

    class Meta:
        verbose_name = 'ユーザープロフィール'
        verbose_name_plural = 'ユーザープロフィール'
        ordering = ['order', 'phonetic_family_name']

    @property
    def full_name(self):
        return f'{self.family_name} {self.given_name}'.strip()

    def __str__(self):
        return self.full_name or self.user.username

    def save(self, *args, **kwargs):
        # 新規作成時かつ表示順が未設定(0)の場合、自動インクリメント
        if not self.pk and self.order == 0:
            max_order = UserProfile.objects.aggregate(models.Max('order'))['order__max']
            self.order = (max_order or 0) + 1

        # システムロールに基づいて User の権限を同期
        if self.system_role == self.SystemRole.ADMIN:
            if not self.user.is_staff or not self.user.is_superuser:
                User.objects.filter(pk=self.user_id).update(is_staff=True, is_superuser=True)
        else:
            if self.user.is_staff or self.user.is_superuser:
                User.objects.filter(pk=self.user_id).update(is_staff=False, is_superuser=False)
        super().save(*args, **kwargs)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)
