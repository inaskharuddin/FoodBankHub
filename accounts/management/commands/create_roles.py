from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group


class Command(BaseCommand):
    help = "Create FoodBankHub user roles"

    def handle(self, *args, **kwargs):

        roles = [
            "Admin",
            "Provider",
            "Donor",
            "Supplier",
            "Needy",
        ]

        for role in roles:
            group, created = Group.objects.get_or_create(name=role)

            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created role: {role}")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"Role already exists: {role}")
                )

        self.stdout.write(
            self.style.SUCCESS("All FoodBankHub roles are ready.")
        )