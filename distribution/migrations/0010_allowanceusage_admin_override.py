from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("distribution", "0009_dataretentionpolicy"),
    ]

    operations = [
        migrations.AddField(
            model_name="allowanceusage",
            name="admin_override",
            field=models.BooleanField(default=False),
        ),
    ]
