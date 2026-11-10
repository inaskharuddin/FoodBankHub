from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_user_phone"),
    ]

    operations = [
        migrations.AlterField(
            model_name="supplier",
            name="ssm_registration_no",
            field=models.CharField(max_length=50, unique=True),
        ),
    ]
