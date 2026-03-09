from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('productions', '0008_vehiclerequest_add_requested_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehiclerequest',
            name='request_kind',
            field=models.CharField(
                choices=[('load_in', '搬入'), ('pickup', '引き取り'), ('other', 'その他')],
                default='load_in',
                max_length=20,
                verbose_name='申請種別',
            ),
        ),
    ]
