from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('productions', '0010_vehiclerequest_route_from'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehiclerequest',
            name='route_to',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='目的地'),
        ),
    ]
