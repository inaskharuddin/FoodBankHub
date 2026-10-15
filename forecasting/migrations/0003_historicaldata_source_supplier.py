from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_needy"),
        ("forecasting", "0002_forecast"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicaldata",
            name="source",
            field=models.CharField(
                choices=[("ACTUAL", "Actual"), ("ESTIMATED", "Estimated")],
                default="ACTUAL",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="historicaldata",
            name="supplier",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="historical_data",
                to="accounts.supplier",
            ),
        ),
        migrations.AddIndex(
            model_name="historicaldata",
            index=models.Index(fields=["provider", "date"], name="forecast_h_provider_4aa923_idx"),
        ),
    ]
