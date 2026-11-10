from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0005_lowstockalert_is_read_lowstockalert_message_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="supplierproduct",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="supplier_products/"),
        ),
    ]
