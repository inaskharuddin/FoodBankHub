from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0003_payout"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseorder",
            name="delivery_confirmed",
            field=models.BooleanField(default=False),
        ),
    ]
