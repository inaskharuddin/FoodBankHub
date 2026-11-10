from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_supplier_approval"),
    ]

    operations = [
        migrations.AddField(
            model_name="provider",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="provider",
            name="is_approved",
            field=models.BooleanField(default=True),
        ),
    ]
