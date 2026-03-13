from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('productions', '0023_processday_setup_label'),
    ]

    operations = [
        migrations.AddField(
            model_name='process',
            name='final_performance_date',
            field=models.DateField(blank=True, null=True, verbose_name='最終公演日'),
        ),
        migrations.AddField(
            model_name='process',
            name='final_performance_location',
            field=models.CharField(
                blank=True,
                default='',
                max_length=200,
                verbose_name='最終公演地',
            ),
        ),
    ]
