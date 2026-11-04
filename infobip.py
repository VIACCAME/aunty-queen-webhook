"""Infobip WhatsApp API: an alternative to sending through Meta's Cloud API directly.

Used when WHATSAPP_PROVIDER=infobip. Infobip uses its own JSON formats, so this module
sends in Infobip's format and turns Infobip's inbound webhooks into the same message
shape Meta uses, so the rest of the bot doesn't change.

Env vars:
  INFOBIP_BASE_URL     your personal API base URL from the Infobip portal, e.g. abcd12.api.infobip.com
  INFOBIP_API_KEY      API key from portal.infobip.com > Developers > API keys
  INFOBIP_SENDER       the WhatsApp number registered with Infobip, digits only, e.g. 2376XXXXXXXX
  INFOBIP_WEBHOOK_KEY  a random string; Infobip must call /infobip/webhook?key=<this>
"""
import os

import requests

INFOBIP_BASE_URL = os.environ.get("INFOBIP_BASE_URL", "").strip().removeprefix("https://").rstrip("/")
INFOBIP_API_KEY = os.environ.get("INFOBIP_API_KEY")
INFOBIP_SENDER = os.environ.get("INFOBIP_SENDER", "").strip().lstrip("+")
INFOBIP_WEBHOOK_KEY = os.environ.get("INFOBIP_WEBHOOK_KEY")


def _post(path, payload=None):
    try:
        r = requests.post(
            f"https://{INFOBIP_BASE_URL}{path}",
            headers={
                "Authorization": f"App {INFOBIP_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload,
            timeout=15,
        )
        print(f"[Infobip {r.status_code}]: {r.text}")
        return r
    except Exception as e:
        print(f"Error calling Infobip API: {e}")
        return None


def send_text(recipient_id, text_body):
    return _post("/whatsapp/1/message/text", {
        "from": INFOBIP_SENDER,
        "to": recipient_id,
        "content": {"text": text_body[:4096]},
    })


def send_buttons(recipient_id, body_text, buttons, header_text=None, footer_text=None):
    """Same limits as Meta: max 3 buttons, 20-char titles, 1024-char body."""
    content = {
        "body": {"text": body_text[:1024]},
        "action": {
            "buttons": [
                {"type": "REPLY", "id": b["id"], "title": b["title"][:20]}
                for b in buttons[:3]
            ]
        },
    }
    if header_text:
        content["header"] = {"type": "TEXT", "text": header_text[:60]}
    if footer_text:
        content["footer"] = {"text": footer_text[:60]}
    return _post("/whatsapp/1/message/interactive/buttons", {
        "from": INFOBIP_SENDER,
        "to": recipient_id,
        "content": content,
    })


def mark_as_read(message_id):
    if message_id:
        _post(f"/whatsapp/1/senders/{INFOBIP_SENDER}/message/{message_id}/read")


def webhook_key_ok(key):
    return bool(INFOBIP_WEBHOOK_KEY) and key == INFOBIP_WEBHOOK_KEY


def to_meta_message(result):
    """Turn one Infobip inbound result into the Meta Cloud API message shape the bot reads."""
    m = result.get("message") or {}
    kind = (m.get("type") or "").upper()
    msg = {"from": result.get("from"), "id": result.get("messageId")}
    if kind == "TEXT":
        msg["type"] = "text"
        msg["text"] = {"body": m.get("text", "")}
    elif kind in ("INTERACTIVE_BUTTON_REPLY", "INTERACTIVE_LIST_REPLY"):
        msg["type"] = "interactive"
        msg["interactive"] = {
            "type": "button_reply",
            "button_reply": {"id": m.get("id", ""), "title": m.get("title", "")},
        }
    elif kind == "BUTTON":
        # Quick-reply button on a template message: treat the button text as typed text.
        msg["type"] = "text"
        msg["text"] = {"body": m.get("text") or m.get("payload") or ""}
    else:
        msg["type"] = kind.lower() or "unknown"
    return msg


ECHO_MARKER_FIELDS = ("event", "eventType", "type", "origin", "direction", "source", "integrationType")


def _looks_like_echo(result):
    for field in ECHO_MARKER_FIELDS:
        value = result.get(field)
        if isinstance(value, str) and ("ECHO" in value.upper() or "BUSINESS_APP" in value.upper()):
            return True
    return False


def split_webhook(data):
    """Return (client_messages, staff_echoes) from an Infobip webhook body.

    Subscribe both "Inbound message" and "Business app message echo" to this webhook.
    Infobip's echo format isn't in its public API reference, so an echo is recognised
    either by coming "from" our own number or by an "echo"/"business app" marker.
    Anything unrecognised is logged (field names only) so the format can be checked.
    """
    client_messages, staff_echoes = [], []
    results = data.get("results")
    if not isinstance(results, list):
        print(f"[Infobip] unrecognised webhook, top-level keys: {sorted(data.keys())}")
        return client_messages, staff_echoes
    for result in results:
        sender = (result.get("from") or "").lstrip("+")
        to = (result.get("to") or "").lstrip("+")
        from_us = bool(INFOBIP_SENDER) and sender == INFOBIP_SENDER
        if from_us or _looks_like_echo(result):
            client = to if from_us or to != INFOBIP_SENDER else sender
            text = (result.get("message") or {}).get("text") or result.get("text") or ""
            if isinstance(text, dict):
                text = text.get("body", "")
            print(f"[Infobip] staff echo for {client}, fields: {sorted(result.keys())}")
            staff_echoes.append({"to": client, "text": {"body": text}})
            continue
        if INFOBIP_SENDER and to and to != INFOBIP_SENDER:
            continue  # a different number on the same Infobip account
        if "message" not in result:
            print(f"[Infobip] result without message, fields: {sorted(result.keys())}")
            continue
        client_messages.append(to_meta_message(result))
    return client_messages, staff_echoes
