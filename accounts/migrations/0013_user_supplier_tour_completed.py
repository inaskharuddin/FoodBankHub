from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_user_provider_tour_completed"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="supplier_tour_completed",
            field=models.BooleanField(default=False),
        ),
    ]
