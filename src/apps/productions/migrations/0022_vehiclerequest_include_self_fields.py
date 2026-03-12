from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('productions', '0021_vehiclerequest_loading_unloading_qty'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehiclerequest',
            name='loading_include_self',
            field=models.BooleanField(default=False, verbose_name='荷積み本人含む'),
        ),
        migrations.AddField(
            model_name='vehiclerequest',
            name='unloading_include_self',
            field=models.BooleanField(default=False, verbose_name='荷降ろし本人含む'),
        ),
    ]
