from calendar import monthrange
from datetime import date

from django.core.management.base import BaseCommand
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from distribution.models import AllowanceUsage, DataRetentionPolicy, Report
from forecasting.models import HistoricalData


def months_before(day, months):
    absolute = day.year * 12 + day.month - 1 - months
    year, month0 = divmod(absolute, 12)
    month = month0 + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


class Command(BaseCommand):
    help = "Remove self-reports and derived actual demand older than the configured retention period."

    def handle(self, *args, **options):
        policy = DataRetentionPolicy.current()
        if not policy.enabled:
            self.stdout.write("Self-report retention is disabled.")
            return
        cutoff = months_before(timezone.localdate(), policy.retention_months)
        expired_report_days = Report.objects.filter(
            report_method="SELF_REPORT", reported_at__date__lt=cutoff,
            provider_id=OuterRef("provider_id"), item_id=OuterRef("item_id"),
            reported_at__date=OuterRef("date"),
        ).values("reported_at__date")
        deleted_history, _ = HistoricalData.objects.filter(
            source=HistoricalData.Source.ACTUAL, date__lt=cutoff,
        ).filter(date__in=Subquery(expired_report_days)).delete()
        deleted_reports, _ = Report.objects.filter(report_method="SELF_REPORT", reported_at__date__lt=cutoff).delete()
        deleted_usage, _ = AllowanceUsage.objects.filter(week_start_date__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(
            f"Removed data before {cutoff}: {deleted_reports} report records, "
            f"{deleted_history} actual-demand records, {deleted_usage} allowance records."
        ))
