from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    """ユーザーごとの追加情報（システムロール、プロフィールなど）"""

    class SystemRole(models.TextChoices):
        ADMIN = 'admin', '管理者'
        EDITOR = 'editor', '編集者'
        GENERAL = 'general', '一般'
        VIEWER = 'viewer', '閲覧者'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    # システム全体のロール（公演内ロール Planner/Chief/Sub とは別管理）
    system_role = models.CharField(
        max_length=20,
        choices=SystemRole.choices,
        default=SystemRole.GENERAL,
        verbose_name='システムロール',
    )

    # ポータル連携用UUID（portal_uuid = User.username on shin•on Portal）
    portal_uuid = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        verbose_name='ポータルUUID',
        help_text='shin•on Portal の portal_uuid（不変ID）。JWT 連携時に自動設定される。',
    )

    # shin•on Portal から同期する情報（JWT クレームより自動更新）
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

    class Meta:
        verbose_name = 'ユーザープロフィール'
        verbose_name_plural = 'ユーザープロフィール'

    def __str__(self):
        return f'{self.full_name or self.user.username} ({self.get_system_role_display()})'

    def save(self, *args, **kwargs):
        # システムロールに基づいて User の権限を同期
        # post_save シグナルの再帰発火を防ぐため update() を使用（save() は呼ばない）
        if self.system_role == self.SystemRole.ADMIN:
            if not self.user.is_staff or not self.user.is_superuser:
                User.objects.filter(pk=self.user_id).update(is_staff=True, is_superuser=True)
        else:
            if self.user.is_staff or self.user.is_superuser:
                User.objects.filter(pk=self.user_id).update(is_staff=False, is_superuser=False)
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return f'{self.family_name} {self.given_name}'.strip() or self.user.first_name

    @property
    def full_kana(self):
        return f'{self.phonetic_family_name} {self.phonetic_given_name}'.strip()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    # 新規ユーザー作成時のみ UserProfile を作成する
    # get_or_create は post_save の再帰呼び出しを誘発するため使用禁止
    if created:
        UserProfile.objects.create(user=instance)
