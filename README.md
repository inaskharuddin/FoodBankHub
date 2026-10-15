# FoodBankHub

FoodBankHub is a Django project for coordinating food bank needs, donations, suppliers, purchase orders, and deliveries.

## Local setup

1. Install Python 3.13 and MySQL, then create a MySQL database named `foodbankhub_db`.
2. Create and activate a virtual environment, then install `requirements.txt`.
3. Set environment variables for `DJANGO_SECRET_KEY`, `DB_PASSWORD`, and `DJANGO_DEBUG=true`. Set `DJANGO_ALLOWED_HOSTS` to `127.0.0.1,localhost` for local testing.
4. Run `python manage.py migrate` and `python manage.py runserver`.
5. Open `http://127.0.0.1:8000/`.

## Billplz sandbox

The donation checkout uses Billplz's sandbox API. Set `BILLPLZ_SANDBOX_API_KEY`, `BILLPLZ_SANDBOX_COLLECTION_ID`, and `BILLPLZ_X_SIGNATURE_KEY`. For callback testing, set `BILLPLZ_PUBLIC_BASE_URL` to an HTTPS tunnel address that reaches the local Django server. Never commit `.env` or live credentials.

## Notes

This repository is a development project and is not configured for production deployment. Use sandbox credentials only for testing.
