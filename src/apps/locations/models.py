"""
場所マスタモデル

劇場・スタジオ等の場所情報を管理する。
"""

from django.db import models


class Location(models.Model):
    """場所マスタ"""

    sort = models.PositiveIntegerField(default=0, verbose_name="表示順")
    name = models.CharField(max_length=200, verbose_name="場所名")
    furigana = models.CharField(
        max_length=200, blank=True, default="", verbose_name="ふりがな"
    )
    postal_code = models.CharField(
        max_length=10, blank=True, default="", verbose_name="郵便番号"
    )
    address = models.CharField(
        max_length=255, blank=True, default="", verbose_name="住所"
    )
    note = models.TextField(blank=True, default="", verbose_name="備考")
    is_active = models.BooleanField(default=True, verbose_name="有効")
    shin_on_db_id = models.IntegerField(
        null=True,
        blank=True,
        unique=True,
        verbose_name="shin-on_db ID",
        help_text="shin-on_db からの同期元ID（手動登録レコードは空）",
    )
    created_at = models.DateTimeField(verbose_name="作成日時")
    updated_at = models.DateTimeField(verbose_name="更新日時")

    class Meta:
        verbose_name = "場所"
        verbose_name_plural = "場所マスタ"
        ordering = ["sort", "name"]

    def __str__(self):
        return self.name
