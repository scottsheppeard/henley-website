# Google account scripts

Small scripts that read and change The Henley's Google Analytics and Tag
Manager setup through Google's APIs, so the changes are reviewable and
repeatable instead of clicks in a dashboard.

They sign in as the service account `keystone@henley-tracking.iam.gserviceaccount.com`
(Google Cloud project `henley-tracking`, created 2026-10-07 under
`thehenleyonbroadwater@gmail.com`). Its key file is not in this repository:
the scripts read `GOOGLE_APPLICATION_CREDENTIALS`, defaulting to
`~/henley-tracking-4481ec639791.json`. What the account may do is whatever it
has been granted inside Analytics (account `thehenley`) and Tag Manager
(container `GTM-PGSH3HF7`), nothing more.

    python3 -m venv ~/.venvs/henley-google
    ~/.venvs/henley-google/bin/pip install google-api-python-client google-auth

Every script is a dry run that prints what it would change. Add `--apply` to
make the changes.

| Script | What it does |
|---|---|
| `ga_settings.py` | Event data retention to 14 months, the stream URL, email redaction, scroll/outbound-click/download measurement, and `generate_lead` as a key event. |
| `gtm_enquiry.py` | Builds the enquiry conversion in the container's workspace. It never publishes; publishing is a person pressing Submit in Tag Manager. |

Google Ads has no script here: its API needs a developer token Google approves
separately, and the campaigns are run by the marketing partner.
