from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("urgent_needs", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="urgentneed",
            name="provider_managed",
            field=models.BooleanField(default=False),
        ),
    ]
