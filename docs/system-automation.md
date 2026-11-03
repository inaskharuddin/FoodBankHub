# FoodBankHub system automation

## Local Windows schedules

Run `scripts/register_automation_tasks.ps1` from an elevated PowerShell session to register:

- Daily provider automation at 6:00 AM: saves 7- and 30-day forecast snapshots, refreshes forecast accuracy and urgent needs, updates low-stock notifications, and runs configured self-report retention.
- Weekly forecast refresh on Sunday at 2:00 AM.
- Compressed MySQL backup on Sunday at 3:00 AM.

The scheduled tasks use this checkout's virtual environment. The computer, MySQL service, and network access to any configured email/payment services must be available at run time. Backups are written to `backups/` by default and rotated to the most recent 12. Set `FOODBANKHUB_BACKUP_DIR`, `FOODBANKHUB_BACKUP_KEEP`, or `MYSQLDUMP_PATH` in the scheduled-task environment to change those defaults.

## Email and FPX sandbox

Provider low-stock emails and donor PDF receipt emails require `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` in the environment available to Django and its scheduled tasks. Without these, alerts remain visible in the Provider page and receipts remain downloadable in donor history.

Sandbox checkout requires `BILLPLZ_SANDBOX_API_KEY`, `BILLPLZ_SANDBOX_COLLECTION_ID`, `BILLPLZ_X_SIGNATURE_KEY`, and a publicly reachable `BILLPLZ_PUBLIC_BASE_URL` for callbacks. Use Billplz sandbox credentials only for development. Donors pay the platform; supplier payout remains an admin action after Provider delivery confirmation.

The automated receipt is a payment receipt only. FoodBankHub does not issue an LHDN tax statement or certify tax deductibility.
