from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('productions', '0020_vehiclerequest_add_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehiclerequest',
            name='loading_qty',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='荷積み人数'),
        ),
        migrations.AddField(
            model_name='vehiclerequest',
            name='unloading_qty',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='荷降ろし人数'),
        ),
    ]
