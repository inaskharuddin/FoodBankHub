import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_needy"),
        ("forecasting", "0003_historicaldata_source_supplier"),
    ]

    operations = [
        migrations.CreateModel(
            name="ForecastRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("forecast_days", models.PositiveSmallIntegerField(default=30)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("provider", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="forecast_runs", to="accounts.provider")),
            ],
            options={
                "ordering": ("-created_at", "-pk"),
            },
        ),
        migrations.AddField(
            model_name="forecast",
            name="run",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="forecasts", to="forecasting.forecastrun"),
        ),
    ]
