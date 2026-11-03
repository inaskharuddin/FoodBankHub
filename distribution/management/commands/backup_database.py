import gzip
import os
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a compressed MySQL database backup."

    def handle(self, *args, **options):
        db = settings.DATABASES["default"]
        if db["ENGINE"] != "django.db.backends.mysql":
            raise CommandError("This backup command currently supports MySQL only.")
        executable = os.environ.get("MYSQLDUMP_PATH", "mysqldump")
        output_dir = Path(os.environ.get("FOODBANKHUB_BACKUP_DIR", settings.BASE_DIR / "backups"))
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = output_dir / f"foodbankhub-{stamp}.sql.gz"
        env = os.environ.copy()
        env["MYSQL_PWD"] = str(db.get("PASSWORD", ""))
        command = [executable, "--host", str(db.get("HOST", "localhost")), "--port", str(db.get("PORT", "3306")), "--user", str(db["USER"]), "--single-transaction", "--routines", "--events", str(db["NAME"])]
        try:
            result = subprocess.run(command, env=env, check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise CommandError("mysqldump failed. Confirm MySQL client tools and database access.") from exc
        with gzip.open(destination, "wb") as target:
            target.write(result.stdout)
        keep = max(1, int(os.environ.get("FOODBANKHUB_BACKUP_KEEP", "12")))
        backups = sorted(output_dir.glob("foodbankhub-*.sql.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[keep:]:
            old.unlink()
        self.stdout.write(self.style.SUCCESS(f"Database backup created: {destination}"))
