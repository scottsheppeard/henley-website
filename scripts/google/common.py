"""Shared setup for the Google account scripts. See README.md in this directory."""

import json
import os
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

KEY = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    os.path.expanduser("~/henley-tracking-4481ec639791.json"),
)

PROPERTY = "properties/398547918"
STREAM = PROPERTY + "/dataStreams/5873509418"
MEASUREMENT_ID = "G-YRX87W827V"

GTM_ACCOUNT = "accounts/6221327270"
GTM_CONTAINER = GTM_ACCOUNT + "/containers/179782643"   # GTM-PGSH3HF7
GTM_WORKSPACE = GTM_CONTAINER + "/workspaces/3"

LIVE_HOSTNAME = "thehenley.com.au"

APPLY = "--apply" in sys.argv


def service(api: str, version: str, *scopes: str):
    credentials = service_account.Credentials.from_service_account_file(
        KEY, scopes=["https://www.googleapis.com/auth/" + scope for scope in scopes]
    )
    return build(api, version, credentials=credentials, cache_discovery=False)


def explain(error: HttpError) -> str:
    try:
        message = json.loads(error.content.decode()).get("error", {}).get("message", "")
    except ValueError:
        message = ""
    return f"{error.resp.status} {message[:300]}"


def change(label: str, current, wanted, apply):
    """Report one setting, and change it only under --apply.

    `apply` is called with no arguments and returns the API's answer.
    """
    if current == wanted:
        print(f"same    {label}: {current}")
        return
    if not APPLY:
        print(f"WOULD   {label}: {current} -> {wanted}")
        return
    try:
        apply()
        print(f"changed {label}: {current} -> {wanted}")
    except HttpError as error:
        print(f"FAILED  {label}: {explain(error)}")
        sys.exit(1)
