from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("donations", "0007_providerreview_and_more"), ("orders", "0007_inventorylot")]
    operations = [
        migrations.AddField(model_name="donationitem", name="link_tracking_enabled", field=models.BooleanField(default=True)),
        migrations.RunPython(lambda apps, schema_editor: apps.get_model("donations", "DonationItem").objects.update(link_tracking_enabled=False), migrations.RunPython.noop),
        migrations.CreateModel(name="DonationOrderAllocation", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("quantity", models.PositiveIntegerField()),
            ("donation_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="order_allocations", to="donations.donationitem")),
            ("purchase_order_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="donation_allocations", to="orders.poitem")),
        ]),
        migrations.AddConstraint(model_name="donationorderallocation", constraint=models.CheckConstraint(check=models.Q(quantity__gt=0), name="donation_order_allocation_positive")),
    ]
