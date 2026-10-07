"""Analytics settings for thehenley.com.au. Dry run unless --apply.

    ~/.venvs/henley-google/bin/python scripts/google/ga_settings.py [--apply]
"""

from common import APPLY, PROPERTY, STREAM, change, service

SCOPE = "analytics.edit" if APPLY else "analytics.readonly"
beta = service("analyticsadmin", "v1beta", SCOPE)
alpha = service("analyticsadmin", "v1alpha", SCOPE)

retention = beta.properties().getDataRetentionSettings(
    name=PROPERTY + "/dataRetentionSettings").execute()
change(
    "event data retention", retention.get("eventDataRetention"), "FOURTEEN_MONTHS",
    lambda: beta.properties().updateDataRetentionSettings(
        name=PROPERTY + "/dataRetentionSettings", updateMask="eventDataRetention",
        body={"eventDataRetention": "FOURTEEN_MONTHS"}).execute(),
)

stream = beta.properties().dataStreams().get(name=STREAM).execute()
change(
    "stream URL", stream["webStreamData"].get("defaultUri"), "https://thehenley.com.au",
    lambda: beta.properties().dataStreams().patch(
        name=STREAM, updateMask="webStreamData.defaultUri",
        body={"webStreamData": {"defaultUri": "https://thehenley.com.au"}}).execute(),
)

redaction = alpha.properties().dataStreams().getDataRedactionSettings(
    name=STREAM + "/dataRedactionSettings").execute()
change(
    "email redaction", redaction.get("emailRedactionEnabled", False), True,
    lambda: alpha.properties().dataStreams().updateDataRedactionSettings(
        name=STREAM + "/dataRedactionSettings", updateMask="emailRedactionEnabled",
        body={"emailRedactionEnabled": True}).execute(),
)

# Form interactions stays off: it counts attempts and spam beside real
# enquiries, which generate_lead now measures properly. The site has no search.
measurement = alpha.properties().dataStreams().getEnhancedMeasurementSettings(
    name=STREAM + "/enhancedMeasurementSettings").execute()
for field in ("scrollsEnabled", "outboundClicksEnabled", "fileDownloadsEnabled"):
    change(
        f"enhanced measurement {field}", measurement.get(field, False), True,
        lambda field=field: alpha.properties().dataStreams().updateEnhancedMeasurementSettings(
            name=STREAM + "/enhancedMeasurementSettings", updateMask=field,
            body={field: True}).execute(),
    )

# The enquiry, as a key event. Fed by the GA4 event tag gtm_enquiry.py builds.
key_events = [k["eventName"] for k in beta.properties().keyEvents().list(
    parent=PROPERTY).execute().get("keyEvents", [])]
change(
    "key event generate_lead", "generate_lead" in key_events, True,
    lambda: beta.properties().keyEvents().create(
        parent=PROPERTY,
        body={"eventName": "generate_lead", "countingMethod": "ONCE_PER_EVENT"}).execute(),
)
print("key events now:", ", ".join(sorted(key_events)) + ("" if "generate_lead" in key_events else " (+ generate_lead under --apply)"))
