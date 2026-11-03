# Weekly forecast retraining

FoodBankHub already provides the Django management command
`retrain_weekly_forecasts`. It retrains forecasts for each provider and refreshes
urgent needs. Run that command from the deployed project directory with the same
Python environment and database access as the web application.

## Current local Windows setup

The local development host uses Windows Task Scheduler. The task
`FoodBankHub Weekly Forecast Retraining` has been created and manually run
successfully. It starts every Sunday at 2:00 AM local time with:

- Program: `C:\Users\inask\FoodBankHub\venv\Scripts\python.exe`
- Arguments: `manage.py retrain_weekly_forecasts`
- Start in: `C:\Users\inask\FoodBankHub`

The computer must be on and awake for the task to run. In Task Scheduler, a
last result of `(0x0)` indicates success. This task runs only on this Windows
computer.

After updating the project with snapshot support, apply its database migration
once from PowerShell in the project directory before the next scheduled run:

```powershell
python manage.py migrate
```

## Linux server with cron

For a future Linux deployment, these instructions assume a Linux server using
cron. The example runs every Sunday at 02:00 UTC; the Django project also uses
UTC. Change the cron time if the server's maintenance window differs.

1. On the server, confirm the deployed project directory and virtual environment
   paths. The commands below assume `/srv/foodbankhub` and
   `/srv/foodbankhub/venv`. Replace those paths with the actual deployment paths.
2. Apply database migrations after deploying code updates:

   ```sh
   cd /srv/foodbankhub
   /srv/foodbankhub/venv/bin/python manage.py migrate
   ```

3. Run the command once manually as the same OS account used by the web app:

   ```sh
   cd /srv/foodbankhub
   /srv/foodbankhub/venv/bin/python manage.py retrain_weekly_forecasts
   ```

4. Create a log file writable by that account. For example, as an administrator,
   replace `foodbankhub` with the deployment account:

   ```sh
   sudo install -o foodbankhub -g foodbankhub -m 0640 /dev/null /var/log/foodbankhub-forecast-retraining.log
   ```

5. Install the weekly cron entry for that deployment account (replace
   `foodbankhub` with the actual account):

   ```sh
   sudo crontab -u foodbankhub -e
   ```

   Add this line:

   ```cron
   0 2 * * 0 cd /srv/foodbankhub && /srv/foodbankhub/venv/bin/python manage.py retrain_weekly_forecasts >> /var/log/foodbankhub-forecast-retraining.log 2>&1
   ```

6. Confirm the entry is installed and inspect the log after the next scheduled
   run:

   ```sh
   sudo crontab -u foodbankhub -l
   tail -n 100 /var/log/foodbankhub-forecast-retraining.log
   ```

Cron must be running on the server, and its account must be able to read the
project, run the configured Python environment, and connect to the application
database. Adding this project documentation does not install or enable a job on
the production server; retraining will be automatic only after the server-side
cron entry is installed and verified.
