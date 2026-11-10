from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_supplier_ssm_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="provider_tour_completed",
            field=models.BooleanField(default=False),
        ),
    ]
