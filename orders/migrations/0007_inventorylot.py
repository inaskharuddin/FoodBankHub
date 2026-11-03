from django.db import migrations, models
import django.db.models.deletion


def seed_legacy_stock(apps, schema_editor):
    Inventory = apps.get_model("inventory", "Inventory")
    Lot = apps.get_model("orders", "InventoryLot")
    Lot.objects.bulk_create([
        Lot(inventory_id=row.inventory_id, received_quantity=row.quantity, remaining_quantity=row.quantity)
        for row in Inventory.objects.all().iterator() if row.quantity > 0
    ])


class Migration(migrations.Migration):
    dependencies = [("orders", "0006_purchaseorder_supplier_workflow"), ("inventory", "0003_inventory")]
    operations = [
        migrations.CreateModel(name="InventoryLot", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("received_quantity", models.PositiveIntegerField()), ("remaining_quantity", models.PositiveIntegerField()),
            ("received_at", models.DateTimeField(auto_now_add=True)),
            ("inventory", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lots", to="inventory.inventory")),
            ("purchase_order_item", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="inventory_lots", to="orders.poitem")),
        ]),
        migrations.RunPython(seed_legacy_stock, migrations.RunPython.noop),
    ]
