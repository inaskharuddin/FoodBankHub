from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Needy, Provider, Supplier, User
from distribution.models import ProviderSupplier, Report, ServiceArea
from donations.models import Cart, CartItem, Donation, DonationItem, Transaction
from forecasting.models import Forecast, ForecastRun, HistoricalData
from inventory.models import Inventory, Item, SupplierProduct
from orders.models import POItem, PurchaseOrder
from urgent_needs.models import UrgentNeed


DEMO_PASSWORD = "FoodBankDemo123!"


class Command(BaseCommand):
    help = "Create repeatable Provider, Supplier, Needy, donor, inventory, forecast and order demo records."

    def _user(self, email, name, role):
        user, _ = User.objects.get_or_create(email=email, defaults={"name": name, "role": role})
        user.name, user.role = name, role
        user.is_active = True
        user.set_password(DEMO_PASSWORD)
        user.save()
        return user

    def handle(self, *args, **options):
        provider_user = self._user("demo.provider@foodbankhub.test", "Demo Provider", "PROVIDER")
        provider, _ = Provider.objects.update_or_create(user=provider_user, defaults={
            "food_bank_name": "Demo Community Food Bank", "phone": "0123456789",
            "address": "Jalan Demo, Shah Alam", "operating_hours": "Mon-Fri 09:00-17:00",
            "latitude": Decimal("3.0738"), "longitude": Decimal("101.5183"),
        })
        supplier_user = self._user("demo.supplier@foodbankhub.test", "Demo Supplier", "SUPPLIER")
        supplier, _ = Supplier.objects.update_or_create(user=supplier_user, defaults={
            "business_name": "Demo Fresh Supply", "ssm_registration_no": "DEMO-SSM-001",
            "contact_person": "Demo Contact", "phone": "0123456789",
            "bank_account": "0000000000", "bank_name": "Sandbox Bank", "rating": Decimal("4.50"),
        })
        backup_user = self._user("demo.supplier2@foodbankhub.test", "Backup Supplier", "SUPPLIER")
        backup_supplier, _ = Supplier.objects.update_or_create(user=backup_user, defaults={
            "business_name": "Demo Backup Supplier", "ssm_registration_no": "DEMO-SSM-002",
            "contact_person": "Backup Contact", "phone": "0123456788",
            "bank_account": "0000000001", "bank_name": "Sandbox Bank", "rating": Decimal("4.00"),
        })
        supplier.is_approved = backup_supplier.is_approved = True
        supplier.save(update_fields=["is_approved"])
        backup_supplier.save(update_fields=["is_approved"])
        ProviderSupplier.objects.filter(provider=provider, status="ACTIVE").exclude(supplier=supplier).update(status="INACTIVE")
        ProviderSupplier.objects.update_or_create(provider=provider, supplier=supplier, defaults={"status": "ACTIVE"})
        ProviderSupplier.objects.update_or_create(provider=provider, supplier=backup_supplier, defaults={"status": "INACTIVE"})
        ServiceArea.objects.update_or_create(provider=provider, postcode="43000", defaults={"zone_name": "Shah Alam Central"})
        ServiceArea.objects.update_or_create(provider=provider, postcode="40100", defaults={"zone_name": "Seksyen 2-5"})

        catalog = [
            ("Demo Rice", "Grain", "kg", Decimal("3.20"), 60, 12, 15),
            ("Demo Canned Beans", "Canned food", "can", Decimal("2.50"), 80, 15, 40),
            ("Demo Cooking Oil", "Oil", "bottle", Decimal("7.00"), 35, 8, 3),
        ]
        products = []
        for name, category, unit, price, supplier_stock, threshold, provider_stock in catalog:
            item = Item.objects.filter(name=name, category=category, unit=unit).first()
            if item is None:
                item = Item.objects.create(name=name, category=category, unit=unit)
            product, _ = SupplierProduct.objects.update_or_create(
                supplier=supplier, item=item,
                defaults={"price": price, "stock": supplier_stock, "status": "ACTIVE"},
            )
            SupplierProduct.objects.update_or_create(
                supplier=backup_supplier, item=item,
                defaults={"price": price + Decimal("0.30"), "stock": supplier_stock // 2, "status": "ACTIVE"},
            )
            Inventory.objects.update_or_create(provider=provider, item=item, defaults={
                "quantity": provider_stock, "threshold_level": threshold, "price_per_unit": price,
            })
            products.append((item, product, price, threshold))

        needy_user = self._user("demo.needy@foodbankhub.test", "Demo Needy User", "NEEDY")
        needy, _ = Needy.objects.update_or_create(user=needy_user, defaults={
            "phone": "0123456787", "address": "Demo Street, Shah Alam",
            "postcode": "43000", "city": "Shah Alam", "state": "Selangor",
        })
        donor = self._user("demo.donor@foodbankhub.test", "Demo Donor", "DONOR")
        admin = self._user("demo.admin@foodbankhub.test", "Demo Platform Admin", "ADMIN")
        admin.is_staff = False
        admin.is_superuser = False
        admin.save(update_fields=["is_staff", "is_superuser"])

        today = timezone.localdate()
        # Keep this provider's demo snapshots self-contained and repeatable.
        ForecastRun.objects.filter(provider=provider).delete()
        Forecast.objects.filter(provider=provider, run__isnull=True, forecast_type="DEMO").delete()
        previous_run = ForecastRun.objects.create(provider=provider, forecast_days=30)
        current_run = ForecastRun.objects.create(provider=provider, forecast_days=30)
        for item, product, price, threshold in products:
            for age in range(1, 61):
                day = today - timedelta(days=age)
                quantity = max(1, 4 + ((age * (item.item_id % 7)) % 9))
                HistoricalData.objects.update_or_create(
                    provider=provider, item=item, date=day,
                    defaults={"quantity": quantity, "source": HistoricalData.Source.ACTUAL, "supplier": supplier},
                )
            for offset in range(1, 31):
                day = today + timedelta(days=offset)
                base = Decimal(str(5 + (offset % 4)))
                Forecast.objects.create(provider=provider, item=item, forecast_date=day,
                                        predicted_quantity=base - Decimal("1.00"), forecast_type="DEMO", run=previous_run)
                Forecast.objects.create(provider=provider, item=item, forecast_date=day,
                                        predicted_quantity=base, forecast_type="DEMO", run=current_run)
            for age in (1, 2, 3):
                day = today - timedelta(days=age)
                actual = HistoricalData.objects.get(provider=provider, item=item, date=day).quantity
                Forecast.objects.create(
                    provider=provider, item=item, forecast_date=day,
                    predicted_quantity=Decimal(actual + 1), actual_quantity=Decimal(actual),
                    mape_score=Decimal("10.00"), forecast_type="DEMO", run=current_run,
                )

        rice, rice_product, rice_price, _ = products[0]
        need, _ = UrgentNeed.objects.update_or_create(
            provider=provider, item=rice, status="OPEN",
            defaults={"required_quantity": 30, "funded_quantity": 5, "remaining_quantity": 25,
                      "target_amount": Decimal("96.00"), "funded_amount": Decimal("16.00")},
        )
        cart, _ = Cart.objects.get_or_create(donor=donor, status="COMPLETED", defaults={"total_amount": Decimal("16.00")})
        donation = Donation.objects.filter(donor=donor, cart=cart, status="PAID").first()
        if donation is None:
            donation = Donation.objects.create(donor=donor, cart=cart, total_amount=Decimal("16.00"), status="PAID")
        DonationItem.objects.get_or_create(
            donation=donation, provider=provider, urgent_need=need, item=rice,
            defaults={"quantity": 5, "price": rice_price},
        )
        Transaction.objects.get_or_create(
            donation=donation, payment_method="DEMO-FPX",
            defaults={"amount": Decimal("16.00"), "status": "PAID", "fpx_reference": "DEMO-TX-001"},
        )

        for status in ("PENDING", "ACCEPTED", "SHIPPED", "DELIVERED"):
            order = PurchaseOrder.objects.filter(provider=provider, supplier=supplier, status=status).first()
            if order is None:
                order = PurchaseOrder.objects.create(
                    provider=provider, supplier=supplier,
                    total_amount=(rice_price * 10).quantize(Decimal("0.01")),
                    status=status, delivery_confirmed=False,
                )
            POItem.objects.get_or_create(
                po=order, product=rice_product,
                defaults={"quantity": 10, "price": rice_price, "subtotal": rice_price * 10},
            )

        # A second Provider gives the donor cart isolation rule a real test target.
        second_provider_user = self._user("demo.provider2@foodbankhub.test", "Demo Provider Two", "PROVIDER")
        second_provider, _ = Provider.objects.update_or_create(user=second_provider_user, defaults={
            "food_bank_name": "Demo Northside Food Bank", "phone": "0123456786",
            "address": "Jalan Ujian, Shah Alam", "operating_hours": "Daily 10:00-18:00",
            "latitude": Decimal("3.0900"), "longitude": Decimal("101.5300"),
        })
        ProviderSupplier.objects.update_or_create(provider=second_provider, supplier=backup_supplier,
                                                  defaults={"status": "ACTIVE"})
        noodles, _ = Item.objects.get_or_create(name="Demo Noodles", category="Dry food", unit="pack")
        noodles_product, _ = SupplierProduct.objects.update_or_create(
            supplier=backup_supplier, item=noodles,
            defaults={"price": Decimal("1.80"), "stock": 100, "status": "ACTIVE"},
        )
        Inventory.objects.update_or_create(provider=second_provider, item=noodles, defaults={
            "quantity": 5, "threshold_level": 10, "price_per_unit": noodles_product.price,
        })
        second_need, _ = UrgentNeed.objects.update_or_create(
            provider=second_provider, item=noodles, status="OPEN",
            defaults={"required_quantity": 20, "funded_quantity": 0, "remaining_quantity": 20,
                      "target_amount": Decimal("36.00"), "funded_amount": Decimal("0.00")},
        )

        # Keep a ready-to-checkout, unpaid cart and a failed transaction for retry/admin recovery tests.
        active_cart, _ = Cart.objects.get_or_create(donor=donor, status="ACTIVE", defaults={"total_amount": Decimal("9.60")})
        CartItem.objects.update_or_create(cart=active_cart, urgent_need=need, defaults={
            "provider": provider, "quantity": 3, "price": rice_price, "subtotal": Decimal("9.60"),
        })
        active_cart.total_amount = sum(active_cart.items.values_list("subtotal", flat=True), Decimal("0.00"))
        active_cart.save(update_fields=["total_amount"])
        failed_donation, _ = Donation.objects.get_or_create(
            donor=donor, cart=active_cart, status="FAILED", defaults={"total_amount": active_cart.total_amount},
        )
        Transaction.objects.update_or_create(donation=failed_donation, payment_method="DEMO-FPX",
                                             defaults={"amount": failed_donation.total_amount, "status": "FAILED", "fpx_reference": "DEMO-FAILED-001"})

        if not Report.objects.filter(provider=provider, needy=needy, item=rice).exists():
            Report.objects.create(needy=needy, provider=provider, item=rice, quantity=2,
                                  report_method="DEMO", status="DISTRIBUTED")
            Report.objects.create(needy=needy, provider=provider, item=rice, quantity=1,
                                  report_method="DEMO", status="BLOCKED_ADDRESS")
        from urgent_needs.services import sync_provider_urgent_needs
        sync_provider_urgent_needs(provider)
        self.stdout.write(self.style.SUCCESS("Demo data ready. Login password for all demo accounts: " + DEMO_PASSWORD))
        self.stdout.write("Provider: demo.provider@foodbankhub.test | Supplier: demo.supplier@foodbankhub.test | Needy: demo.needy@foodbankhub.test | Donor: demo.donor@foodbankhub.test | Admin: demo.admin@foodbankhub.test")
        self.stdout.write("Second Provider for cart-isolation tests: demo.provider2@foodbankhub.test")
        self.stdout.write("The active donor cart is test data. Use Billplz sandbox only; payment credentials are not preconfigured.")
