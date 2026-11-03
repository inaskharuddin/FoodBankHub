from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_needy_latitude_needy_longitude"),
    ]

    operations = [
        migrations.AddField(
            model_name="supplier",
            name="is_approved",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="supplier",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
