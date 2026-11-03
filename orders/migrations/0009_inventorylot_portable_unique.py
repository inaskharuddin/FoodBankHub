from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0008_inventorylot_unique_po_item")]
    operations = [
        migrations.RemoveConstraint(model_name="inventorylot", name="unique_inventory_lot_per_po_item"),
        migrations.AddConstraint(model_name="inventorylot", constraint=models.UniqueConstraint(fields=("purchase_order_item",), name="unique_inventory_lot_per_po_item")),
    ]
