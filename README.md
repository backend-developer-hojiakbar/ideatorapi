Ideator Backend (Django REST Framework)

Quick start
- python -m venv .venv && .venv\Scripts\activate (Windows)
- pip install -r requirements.txt
- python manage.py migrate
- python manage.py createsuperuser --phone_number=+998901234567
- python manage.py runserver 0.0.0.0:8000

ENV (optional)
- DJANGO_SECRET_KEY=...
- DEBUG=1

Auth
- POST /api/auth/register {"phone_number":"+998...","password":"..."}
- POST /api/auth/login {"phone_number":"+998...","password":"..."} -> access/refresh
- GET  /api/auth/me  (Bearer access)

Configs / Projects
- POST /api/configs/ {...}  (IdeaConfiguration)
- POST /api/projects/start {"project_name":"...","description":"...","config":1,"data":{...}}  (fee 10000 deducted)
- GET  /api/projects/

Wallet
- POST /api/wallet/topup {"amount": 50000.00}  (1% cashback, notification)

Listings
- POST /api/listings/ {"project": <id>, "funding_sought": 1000000, "equity_offered": 10, "pitch":"..."}
- GET  /api/listings/?all=1  (public)

Notifications
- GET /api/notifications/
- POST /api/notifications/mark-read/

CORS enabled for all origins (adjust in settings).
Custom user uses phone_number as username and keeps balance.
