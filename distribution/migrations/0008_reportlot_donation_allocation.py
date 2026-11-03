from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("distribution", "0007_reportlotallocation"), ("donations", "0008_donationorderallocation")]
    operations = [migrations.AddField(
        model_name="reportlotallocation", name="donation_order_allocation",
        field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="distribution_allocations", to="donations.donationorderallocation"),
    )]
