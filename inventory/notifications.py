import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import LowStockAlert


logger = logging.getLogger(__name__)


def email_new_low_stock_alerts(provider, alerts, forecast_days):
    """Email newly active alerts once per item and forecast period."""
    current_item_ids = {alert["item_id"] for alert in alerts}
    active_records = LowStockAlert.objects.filter(
        provider=provider, forecast_days=forecast_days, is_active=True,
    )
    if current_item_ids:
        active_records = active_records.exclude(item_id__in=current_item_ids)
    active_records.update(is_active=False)

    if not alerts:
        return "clear"
    pending = []
    for alert in alerts:
        state, _ = LowStockAlert.objects.get_or_create(
            provider=provider,
            item_id=alert["item_id"],
            forecast_days=forecast_days,
        )
        state.priority = alert.get("priority", "NORMAL")
        state.message = alert.get("reason", "Low stock")
        newly_active = not state.is_active
        if newly_active:
            state.is_active = True
            state.is_read = False
            state.save(update_fields=["is_active", "is_read", "priority", "message"])
        else:
            state.save(update_fields=["priority", "message"])
        if newly_active or not state.last_sent_at:
            pending.append((state, alert))
    if not pending:
        return "already_sent"

    if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        return "not_configured"

    item_label = "item" if len(pending) == 1 else "items"
    lines = [
        f"FoodBankHub low-stock alert for {provider.food_bank_name}",
        f"Forecast period: {forecast_days} days",
        "",
    ]
    for _, alert in pending:
        lines.extend([
            f"{alert['name']} ({alert['category']})",
            f"Current stock: {alert['current_stock']} {alert['unit']}",
            f"Forecast demand: {alert['forecast_demand']} {alert['unit']}",
            f"Required stock with 20% buffer: {alert['required_stock']} {alert['unit']}",
            f"Suggested order: {alert['suggested_order']} {alert['unit']}",
            "",
        ])
    try:
        sent = send_mail(
            subject=f"FoodBankHub low-stock alert: {len(pending)} {item_label}",
            message="\n".join(lines),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[provider.user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Failed sending low-stock alert email for provider %s", provider.pk)
        return "failed"

    if not sent:
        return "failed"
    sent_at = timezone.now()
    for state, _ in pending:
        state.last_sent_at = sent_at
    pending_states = [state for state, _ in pending]
    LowStockAlert.objects.bulk_update(pending_states, ["last_sent_at"])
    return "sent"
