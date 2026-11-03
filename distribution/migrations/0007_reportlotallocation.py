from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("distribution", "0006_report_submission_key_providerallowance_and_more"), ("orders", "0007_inventorylot")]
    operations = [
        migrations.CreateModel(name="ReportLotAllocation", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("quantity", models.PositiveIntegerField()), ("estimated", models.BooleanField(default=False)),
            ("inventory_lot", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="distribution_allocations", to="orders.inventorylot")),
            ("report", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stock_allocations", to="distribution.report")),
        ]),
    ]
