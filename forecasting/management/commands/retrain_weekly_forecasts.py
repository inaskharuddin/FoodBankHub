from django.core.management.base import BaseCommand
from accounts.models import Provider
from forecasting.services import generate_provider_forecasts
from urgent_needs.services import sync_provider_urgent_needs


class Command(BaseCommand):
    help = "Retrain the Prophet forecast for each Provider (schedule weekly, e.g. every Sunday)."

    def handle(self, *args, **options):
        total = 0
        for provider in Provider.objects.select_related("user"):
            generated, failures = generate_provider_forecasts(provider, 30)
            sync_provider_urgent_needs(provider)
            total += generated
            self.stdout.write(f"{provider.food_bank_name}: {generated} item forecast(s); failures: {', '.join(failures) or 'none'}")
        self.stdout.write(self.style.SUCCESS(f"Weekly retraining completed for {total} item forecast(s)."))
