# TicketFlow Community

TicketFlow Community is an open-source service desk and IT operations dashboard built with Flask and CoreUI. It supports customer tickets, internal support requests, SLA tracking, IT asset governance, 15-to-15 reporting periods, light/dark themes, and optional Google sign-in.

This repository is a clean community edition. It contains no production database, customer records, private reports, credentials, deployment backups, or organization-specific branding.

## Features

- Customer and internal support ticket workflows
- Priorities, normalized categories, modalities, SLA targets, and work hours
- Comments, status tracking, diagnosis, solution, and user validation
- IT assets, licenses, responsibilities, and recurring controls
- Operational periods from the 15th to the following 15th
- PDF and CSV period reports
- Role-based access for administrators, technicians, users, and customers
- Optional Google OpenID Connect with domain restriction
- Responsive UI with persistent light and dark themes
- Jira-style Kanban board with drag-and-drop status updates, search, and filters

## Quick start

Requirements: Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
flask --app run.py create-admin
flask --app run.py run
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

Open `http://127.0.0.1:5000` and sign in with the administrator created by the CLI command.

## Docker

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec ticketflow flask --app run.py create-admin
```

The app is then available at `http://localhost:5005`. SQLite data and reports are stored in the `ticketflow_data` volume.

## Configuration

Copy `.env.example` to `.env` and replace `SECRET_KEY` before deployment. The `.env` file is ignored by Git.

Important variables:

| Variable | Purpose |
| --- | --- |
| `APP_NAME` | Name displayed by the interface |
| `SECRET_KEY` | Flask session signing secret |
| `SQLITE_PATH` | SQLite database location |
| `REPORTS_DIR` | Generated report directory |
| `GOOGLE_CLIENT_ID` | Optional Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Optional Google OAuth secret |
| `GOOGLE_ALLOWED_DOMAIN` | Optional Google Workspace domain restriction |
| `GOOGLE_AUTO_PROVISION` | Creates new Google users when `True`; defaults to `False` |

For production, use HTTPS, a stable secret, regular database backups, and a reverse proxy.

## Google sign-in

Google sign-in is disabled until `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are configured. For an internal deployment, set `GOOGLE_ALLOWED_DOMAIN` and keep `GOOGLE_AUTO_PROVISION=False`; create or approve users from an administrator account before their first sign-in.

The authorized callback URI is:

```text
https://your-domain.example/login/google/callback
```

## Reports

Generate the most recently completed period:

```bash
python scripts/generate_period_report.py
```

Generate a specific period:

```bash
python scripts/generate_period_report.py --start 2026-06-15
```

## Security and privacy

- Never commit `.env`, SQLite databases, reports, backups, or uploaded files.
- Google auto-provisioning is disabled by default.
- Review roles and permissions before exposing the app publicly.
- Report vulnerabilities privately according to [SECURITY.md](SECURITY.md).

## License and attribution

Released under the MIT License. The original dashboard foundation is copyright AppSeed; later TicketFlow Community modifications are distributed under the same license. See [LICENSE](LICENSE).

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

Run the included smoke test before submitting changes:

```bash
python tests/smoke_test.py
```
