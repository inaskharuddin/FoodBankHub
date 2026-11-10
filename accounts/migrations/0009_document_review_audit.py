from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0008_provider_supplier_rejected_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="provider",
            name="documents_reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="provider",
            name="documents_reviewed_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="provider_documents_reviewed", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="supplier",
            name="documents_reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="supplier",
            name="documents_reviewed_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="supplier_documents_reviewed", to=settings.AUTH_USER_MODEL),
        ),
    ]
