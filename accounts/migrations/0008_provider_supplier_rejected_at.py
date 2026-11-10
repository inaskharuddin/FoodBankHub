from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_provider_approval"),
    ]

    operations = [
        migrations.AddField(
            model_name="provider",
            name="rejected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="supplier",
            name="rejected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
