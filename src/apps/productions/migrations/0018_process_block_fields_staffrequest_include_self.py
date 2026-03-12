from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('productions', '0017_processday_date_nullable'),
    ]

    operations = [
        # Process: block_key / sumida_required / assistant_required
        migrations.AddField(
            model_name='process',
            name='block_key',
            field=models.CharField(
                blank=True,
                default='',
                help_text='テンプレート定義のキー（rehearsal_setup等）',
                max_length=50,
                verbose_name='ブロックキー',
            ),
        ),
        migrations.AddField(
            model_name='process',
            name='sumida_required',
            field=models.BooleanField(blank=True, null=True, verbose_name='すみだ便必要'),
        ),
        migrations.AddField(
            model_name='process',
            name='assistant_required',
            field=models.BooleanField(blank=True, null=True, verbose_name='助っ人必要'),
        ),
        # StaffRequest: include_self
        migrations.AddField(
            model_name='staffrequest',
            name='include_self',
            field=models.BooleanField(default=False, verbose_name='本人を含む'),
        ),
        # StaffRequest: verbose_name 変更
        migrations.AlterField(
            model_name='staffrequest',
            name='quantity',
            field=models.PositiveIntegerField(default=1, verbose_name='希望人数'),
        ),
    ]
