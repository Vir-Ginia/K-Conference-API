# K-Conference API

A Django REST API for managing academic conferences, from accounts and submissions through peer reviews, registration and scheduling.

## Features represented in the source

- Account registration, email verification, roles and JSON Web Token (JWT) authentication.
- Conference management, paper submissions and reviewer workflows.
- Conference registration and schedule management.
- Notifications and email templates.
- Analytics, audit records and administration pages.
- SQLite for local development, with environment-based MySQL configuration.
- Optional Cloudinary media storage and Redis caching.

## Source structure

`k_conference/` contains project configuration and URL routing. `apps/` contains `accounts`, `conferences`, `submissions`, `reviews`, `scheduling`, `registrations`, `communications`, `analytics`, `audit` and shared `core` functionality. Database migrations and the supplied demonstration seed command are included.

## Local setup

Use a Python version supported by the Django release pinned in `requirements.txt`.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Set a new local `SECRET_KEY`, then run:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The requirements include `mysqlclient`, which may need MySQL client development libraries even when using the SQLite fallback. A fresh dependency installation and end-to-end service test were not run during this portfolio upload.

## Entry points

| Route | Purpose |
| --- | --- |
| `/api/docs/` | Interactive API documentation |
| `/api/schema/` | OpenAPI schema |
| `/admin/` | Django administration |
| `/api/health/` | Application health |
| `/api/health/db/` | Database health |
| `/api/v1/` | Versioned application endpoints |

## Publication notes

The public source excludes the original environment file, local database, logs, installed packages, assessment scenario and system guide. `.env.example` documents configuration without deployment credentials. The demonstration seed command uses fictional accounts and a shared demonstration password; use `createsuperuser` for your own local account and do not deploy seeded accounts publicly.

Python source syntax was checked for this upload. The original application logic and pinned dependencies are retained.

Virginia Eduwa — conference management project.
