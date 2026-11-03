from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0005_payout_unique_payout_per_purchase_order"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseorder",
            name="rejection_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="purchaseorder",
            name="tracking_number",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="purchaseorder",
            name="delivery_note",
            field=models.TextField(blank=True),
        ),
    ]
