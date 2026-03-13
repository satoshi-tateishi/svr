from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('productions', '0024_process_final_performance_fields'),
    ]

    operations = [
        migrations.RenameField(
            model_name='process',
            old_name='final_performance_date',
            new_name='final_performance_load_out_date',
        ),
        migrations.AlterField(
            model_name='process',
            name='final_performance_load_out_date',
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name='最終公演地搬出日',
            ),
        ),
    ]
