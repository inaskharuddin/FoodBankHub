from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0007_inventorylot")]
    operations = [migrations.AddConstraint(
        model_name="inventorylot",
        constraint=models.UniqueConstraint(fields=("purchase_order_item",), condition=models.Q(purchase_order_item__isnull=False), name="unique_inventory_lot_per_po_item"),
    )]
