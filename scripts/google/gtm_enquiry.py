"""Build the enquiry conversion in the GTM-PGSH3HF7 workspace. Never publishes.

Dry run unless --apply. Safe to run twice: everything is looked up by name.

    ~/.venvs/henley-google/bin/python scripts/google/gtm_enquiry.py [--apply]

What it leaves in the Default Workspace, as unpublished changes:

  - trigger "Enquiry submitted": the custom event `enquiry_submitted`, on the
    live hostname only (dev.thehenley.com.au loads the same container);
  - the 2024 draft tag "PD* Thankyou Page" renamed "Enquiry submitted - Google
    Ads", moved from its page-view trigger to that one, given the enquiry
    reference as its order id and the hashed email/phone as user-provided data;
  - a GA4 event tag sending `generate_lead` on the same trigger;
  - the live hostname condition on the phone-link and email-link triggers;
  - the old page-view trigger deleted. It was never published.

The thank-you page's side of this is replica/site/thank-you/index.html; the
reasoning is docs/decisions.md, "Enquiry conversions".
"""

import sys

from googleapiclient.errors import HttpError

from common import APPLY, GTM_WORKSPACE, LIVE_HOSTNAME, MEASUREMENT_ID, explain, service

tm = service("tagmanager", "v2", "tagmanager.edit.containers" if APPLY else "tagmanager.readonly")
ws = tm.accounts().containers().workspaces()

OLD_TAG, ADS_TAG, GA_TAG = "PD* Thankyou Page", "Enquiry submitted - Google Ads", "Enquiry submitted - GA4 generate_lead"
OLD_TRIGGER, TRIGGER = "PD* Thankyou Page", "Enquiry submitted"
VAR_REF, VAR_DATA, VAR_USER = "DLV - enquiry_ref", "DLV - enquiry_user_data", "Enquiry user-provided data"


def template(key, value):
    return {"type": "template", "key": key, "value": value}


def boolean(key, value):
    return {"type": "boolean", "key": key, "value": "true" if value else "false"}


def condition(kind, left, right):
    return {"type": kind, "parameter": [template("arg0", left), template("arg1", right)]}


HOST_CONDITION = condition("equals", "{{Page Hostname}}", LIVE_HOSTNAME)


def do(label, call):
    if not APPLY:
        print("WOULD  ", label)
        return None
    try:
        result = call()
        print("done   ", label)
        return result
    except HttpError as error:
        print("FAILED ", label, explain(error))
        sys.exit(1)


def by_name(items):
    return {item["name"]: item for item in items}


tags = by_name(ws.tags().list(parent=GTM_WORKSPACE).execute().get("tag", []))
triggers = by_name(ws.triggers().list(parent=GTM_WORKSPACE).execute().get("trigger", []))
variables = by_name(ws.variables().list(parent=GTM_WORKSPACE).execute().get("variable", []))
built_in = {v["type"] for v in ws.built_in_variables().list(parent=GTM_WORKSPACE).execute().get("builtInVariable", [])}

# ── Variables ────────────────────────────────────────────────────────────────
if "pageHostname" in built_in:
    print("same    built-in variable Page Hostname")
else:
    do("enable built-in variable Page Hostname",
       lambda: ws.built_in_variables().create(parent=GTM_WORKSPACE, type="pageHostname").execute())

for name, key in ((VAR_REF, "enquiry_ref"), (VAR_DATA, "enquiry_user_data")):
    if name in variables:
        print("same    variable", name)
    else:
        do(f"create data layer variable {name}",
           lambda name=name, key=key: ws.variables().create(parent=GTM_WORKSPACE, body={
               "name": name, "type": "v",
               "parameter": [{"type": "integer", "key": "dataLayerVersion", "value": "2"},
                             boolean("setDefaultValue", False), template("name", key)],
           }).execute())

# The page pushes an object already keyed the way Google's tags expect
# (sha256_email_address, sha256_phone_number), so this variable only passes it on.
if VAR_USER in variables:
    print("same    variable", VAR_USER)
else:
    do(f"create user-provided data variable {VAR_USER}",
       lambda: ws.variables().create(parent=GTM_WORKSPACE, body={
           "name": VAR_USER, "type": "awec",
           "parameter": [template("mode", "CODE"), template("dataSource", "{{%s}}" % VAR_DATA)],
       }).execute())

# ── Trigger ──────────────────────────────────────────────────────────────────
trigger = triggers.get(TRIGGER)
if trigger:
    print("same    trigger", TRIGGER)
else:
    trigger = do(f"create trigger {TRIGGER} (custom event enquiry_submitted, hostname {LIVE_HOSTNAME})",
                 lambda: ws.triggers().create(parent=GTM_WORKSPACE, body={
                     "name": TRIGGER, "type": "customEvent",
                     "customEventFilter": [condition("equals", "{{_event}}", "enquiry_submitted")],
                     "filter": [HOST_CONDITION],
                 }).execute())
trigger_id = trigger["triggerId"] if trigger else "<new>"

# ── The Google Ads conversion ────────────────────────────────────────────────
ads = tags.get(ADS_TAG) or tags.get(OLD_TAG)
if not ads:
    sys.exit(f"neither {ADS_TAG!r} nor {OLD_TAG!r} is in the workspace; nothing to move")
wanted = {
    "orderId": template("orderId", "{{%s}}" % VAR_REF),
    "enableEnhancedConversion": boolean("enableEnhancedConversion", True),
    "cssProvidedEnhancedConversionValue": template("cssProvidedEnhancedConversionValue", "{{%s}}" % VAR_USER),
}
parameters = [p for p in ads.get("parameter", []) if p["key"] not in wanted] + list(wanted.values())
label = next((p["value"] for p in ads.get("parameter", []) if p["key"] == "conversionLabel"), "?")
if (ads["name"] == ADS_TAG and ads.get("firingTriggerId") == [trigger_id]
        and all(p in ads.get("parameter", []) for p in wanted.values())):
    print("same    tag", ADS_TAG)
else:
    body = dict(ads, name=ADS_TAG, firingTriggerId=[trigger_id], parameter=parameters)
    body.pop("fingerprint", None)
    do(f"tag {ads['name']!r} -> {ADS_TAG!r}: trigger {ads.get('firingTriggerId')} -> [{trigger_id}], "
       f"order id + user-provided data (conversion label {label} unchanged)",
       lambda: ws.tags().update(path=ads["path"], body=body).execute())

# ── The Analytics event ──────────────────────────────────────────────────────
if GA_TAG in tags:
    print("same    tag", GA_TAG)
else:
    do(f"create tag {GA_TAG} ({MEASUREMENT_ID})",
       lambda: ws.tags().create(parent=GTM_WORKSPACE, body={
           "name": GA_TAG, "type": "gaawe", "firingTriggerId": [trigger_id],
           "tagFiringOption": "oncePerEvent",
           "parameter": [template("eventName", "generate_lead"),
                         template("measurementIdOverride", MEASUREMENT_ID),
                         boolean("sendEcommerceData", False)],
       }).execute())

# ── Keep the dev site out of the click conversions ───────────────────────────
for name in ("PD - Call (trigger)", "PD - Click To Email"):
    existing = triggers.get(name)
    if not existing:
        print("missing trigger", name)
    elif HOST_CONDITION in existing.get("filter", []):
        print("same    trigger", name)
    else:
        body = dict(existing, filter=existing.get("filter", []) + [HOST_CONDITION])
        body.pop("fingerprint", None)
        do(f"trigger {name!r}: add Page Hostname equals {LIVE_HOSTNAME}",
           lambda existing=existing, body=body: ws.triggers().update(path=existing["path"], body=body).execute())

# ── The page-view trigger the draft tag used ─────────────────────────────────
old = triggers.get(OLD_TRIGGER)
if old and old.get("type") == "pageview":
    do(f"delete unpublished page-view trigger {OLD_TRIGGER!r} (Page URL contains /thank-you/)",
       lambda: ws.triggers().delete(path=old["path"]).execute())
else:
    print("same    old page-view trigger already gone")

status = ws.getStatus(path=GTM_WORKSPACE).execute()
print(f"\nworkspace now holds {len(status.get('workspaceChange', []))} unpublished change(s); nothing was published")
