import hashlib
import hmac
import os
import re
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone

import requests
import ai
import infobip
from messages import MESSAGES, BUTTONS, DEFAULT_NAME
from flask import Flask, request, jsonify, redirect, make_response

import dashboard

from onboarding import onboarding
from privacy import privacy

app = Flask(__name__)
app.register_blueprint(onboarding)
app.register_blueprint(privacy)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
APP_SECRET = os.environ.get("APP_SECRET")  # Meta App > Settings > Basic > App secret (optional but recommended)
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
GRAPH_VERSION = os.environ.get("GRAPH_VERSION", "v23.0")
# "meta" (default) sends through Meta's Cloud API directly; "infobip" sends through Infobip (see infobip.py).
WHATSAPP_PROVIDER = os.environ.get("WHATSAPP_PROVIDER", "meta").strip().lower()
USE_INFOBIP = WHATSAPP_PROVIDER == "infobip"
GOOGLE_SHEET_WEBHOOK_URL = os.environ.get("GOOGLE_SHEET_WEBHOOK_URL")
SHEET_SECRET = os.environ.get("SHEET_SECRET", "")
# After this many days of silence, a conversation that was handed to a human starts a fresh intake.
HUMAN_MODE_RESET_DAYS = float(os.environ.get("HUMAN_MODE_RESET_DAYS", "30"))
# After this many side questions answered by the AI in one intake, a counselor takes over.
AI_MAX_QUESTIONS = int(os.environ.get("AI_MAX_QUESTIONS", "8"))

# Staff type these from the WhatsApp Business app (coexistence) to give a chat back to the bot.
BOT_RESUME_COMMANDS = {"#bot", "#done"}
# Clients can type this to start the intake again.
CLIENT_RESTART_WORDS = {"restart", "recommencer"}
# Clients can type this to ask for their data to be deleted (see /privacy).
DELETE_WORDS = {"delete", "supprimer"}

# In-memory cache; the Google Sheet "Sessions" tab is the source of truth across restarts.
sessions = {}
session_locks = {}
locks_guard = threading.Lock()
seen_message_ids = OrderedDict()
seen_guard = threading.Lock()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# =============================================================================
# META CLOUD API
# =============================================================================
def get_graph_url():
    return f"https://graph.facebook.com/{GRAPH_VERSION}/{PHONE_NUMBER_ID}/messages"


def get_headers():
    return {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }


def send_meta_request(payload):
    try:
        r = requests.post(get_graph_url(), headers=get_headers(), json=payload, timeout=15)
        print(f"[API Response {r.status_code}]: {r.text}")
        return r
    except Exception as e:
        print(f"Error calling Meta API: {e}")
        return None


TYPING_DELAY = float(os.environ.get("TYPING_DELAY", "1"))  # 0 turns the pause off


def pause_like_typing(text):
    """A short, natural pause before each message, longer for longer messages (max ~3.5 s).
    Urgent safety messages go out straight away."""
    if TYPING_DELAY <= 0 or (text or "").startswith("🚨"):
        return
    time.sleep(TYPING_DELAY * min(0.8 + len(text or "") / 250, 3.5))


def send_text(recipient_id, text_body):
    log_message(recipient_id, "bot", text_body)
    pause_like_typing(text_body)
    if USE_INFOBIP:
        return infobip.send_text(recipient_id, text_body)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_id,
        "type": "text",
        "text": {"body": text_body}
    }
    return send_meta_request(payload)


def send_buttons(recipient_id, body_text, buttons, header_text=None, footer_text=None):
    """WhatsApp button limits: max 3 buttons, max 20 chars title, max 1024 chars body."""
    log_message(recipient_id, "bot", body_text + "  [" + " | ".join(b["title"] for b in buttons[:3]) + "]")
    pause_like_typing(body_text)
    if USE_INFOBIP:
        return infobip.send_buttons(recipient_id, body_text, buttons, header_text, footer_text)
    interactive_obj = {
        "type": "button",
        "body": {"text": body_text[:1024]},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
                for b in buttons[:3]
            ]
        }
    }
    if header_text:
        interactive_obj["header"] = {"type": "text", "text": header_text[:60]}
    if footer_text:
        interactive_obj["footer"] = {"text": footer_text[:60]}

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_id,
        "type": "interactive",
        "interactive": interactive_obj
    }
    return send_meta_request(payload)


def send_list(recipient_id, body_text, button_label, rows):
    """A list message: up to 10 rows, row titles max 24 chars, button label max 20 chars."""
    log_message(recipient_id, "bot", body_text + "  [" + " | ".join(r["title"] for r in rows[:10]) + "]")
    pause_like_typing(body_text)
    if USE_INFOBIP:
        return infobip.send_list(recipient_id, body_text, button_label, rows)
    return send_meta_request({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_id,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body_text[:1024]},
            "action": {"button": button_label[:20], "sections": [{"title": button_label[:24], "rows": [
                {"id": r["id"], "title": r["title"][:24]} for r in rows[:10]]}]},
        },
    })


def send_template(recipient_id, template_name, language_code):
    """A pre-approved WhatsApp template (needed to message someone outside the 24-hour window)."""
    log_message(recipient_id, "bot", f"[template {template_name}]")
    if USE_INFOBIP:
        return infobip.send_template(recipient_id, template_name, language_code)
    return send_meta_request({
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "type": "template",
        "template": {"name": template_name, "language": {"code": language_code}},
    })


def mark_as_read(message_id):
    if USE_INFOBIP:
        return infobip.mark_as_read(message_id)
    # On Meta's Cloud API this also shows "typing…" until the next reply (Infobip has no equivalent).
    send_meta_request({"messaging_product": "whatsapp", "status": "read", "message_id": message_id,
                       "typing_indicator": {"type": "text"}})


# =============================================================================
# GOOGLE SHEET (Apps Script web app, see google_apps_script.gs)
# =============================================================================
def sheet_call(action, payload):
    if not GOOGLE_SHEET_WEBHOOK_URL:
        return None
    try:
        r = requests.post(
            GOOGLE_SHEET_WEBHOOK_URL,
            json={"action": action, "secret": SHEET_SECRET, **payload},
            headers={"Content-Type": "application/json"},
            allow_redirects=True,
            timeout=20
        )
        return r.json()
    except Exception as e:
        print(f"Google Sheet error ({action}): {e}")
        return None


def log_message(phone, direction, text, step=None, intake_id=None):
    """Every message in and out goes to the Sheet's Messages tab (in the background, so replies stay fast)."""
    if not GOOGLE_SHEET_WEBHOOK_URL or not phone:
        return
    row = {"time": now_iso(), "phone": phone, "direction": direction, "text": (text or "")[:2000],
           "step": step or "", "intake_id": intake_id or ""}
    threading.Thread(target=sheet_call, args=("log_messages", {"rows": [row]}), daemon=True).start()


# Profile details kept per person, so returning clients aren't asked again.
PROFILE_FIELDS = ("name", "language", "consent", "age", "gender", "city", "education", "pregnancies_children",
                  "heard_from")
contacts = {}


def load_contact(phone):
    if phone in contacts:
        return contacts[phone]
    result = sheet_call("get_contact", {"phone": phone}) or {}
    contact = result.get("contact")
    if contact:
        contact = {k: (str(v).lstrip("'") if v is not None else "") for k, v in contact.items()}
        contacts[phone] = contact
    return contact


def save_contact(phone, **fields):
    contact = contacts.setdefault(phone, {"phone": phone})
    contact.update({k: v for k, v in fields.items() if v not in (None, "")})
    row = dict(contact, phone=phone)
    threading.Thread(target=sheet_call, args=("upsert_contact", {"row": row}), daemon=True).start()


def update_contact_from_session(session):
    data = session.get("data", {})
    fields = {k: data.get(k) for k in PROFILE_FIELDS if data.get(k) and data.get(k) != "Friend"}
    existing = contacts.get(session["phone"]) or {}
    save_contact(
        session["phone"],
        first_seen=existing.get("first_seen") or session.get("started_at"),
        last_seen=now_iso(),
        last_intake_id=session.get("intake_id"),
        last_status=session.get("status"),
        **fields,
    )


def save_intake(session, **extra):
    """Upsert this person's intake row. Called after every answer so partial intakes are kept."""
    row = {
        "intake_id": session["intake_id"],
        "started_at": session.get("started_at"),
        "updated_at": now_iso(),
        "phone": session["phone"],
        "status": session.get("status", "in_progress"),
        "last_step": session.get("step"),
    }
    row.update(session.get("data", {}))
    row.update(extra)
    sheet_call("upsert_intake", {"row": row})
    update_contact_from_session(session)


def load_session(phone):
    if phone in sessions:
        return sessions[phone]
    result = sheet_call("get_session", {"phone": phone}) or {}
    session = result.get("session")
    if session:
        sessions[phone] = session
    return session


def store_session(session):
    session["updated_at"] = now_iso()
    sessions[session["phone"]] = session
    sheet_call("save_session", {"phone": session["phone"], "session": session})


def new_session(phone):
    return {
        "phone": phone,
        "mode": "bot",          # "bot" or "human"
        "step": None,
        "status": "in_progress",
        "intake_id": uuid.uuid4().hex[:10],
        "started_at": now_iso(),
        "updated_at": now_iso(),
        "data": {"name": "Friend", "language": "en"},
    }


def lock_for(phone):
    with locks_guard:
        if phone not in session_locks:
            session_locks[phone] = threading.Lock()
        return session_locks[phone]


def already_seen(message_id):
    """Meta retries webhooks; never answer the same message twice."""
    if not message_id:
        return False
    with seen_guard:
        if message_id in seen_message_ids:
            return True
        seen_message_ids[message_id] = True
        while len(seen_message_ids) > 5000:
            seen_message_ids.popitem(last=False)
    return False


def hand_to_human(session, status="needs_human"):
    session["mode"] = "human"
    session["status"] = status
    session["step"] = "HUMAN"


# =============================================================================
# WEBHOOK ROUTES
# =============================================================================
@app.route("/", methods=["GET"])
def home():
    return "Aunty Queen Hotline Full Bot Active", 200


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and VERIFY_TOKEN and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403


def signature_ok(raw_body):
    if not APP_SECRET:
        return True
    sent = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sent, expected)


@app.route("/webhook", methods=["POST"])
def receive_webhook():
    raw = request.get_data()
    if not signature_ok(raw):
        return "Bad signature", 403
    data = request.get_json(silent=True) or {}
    # Answer Meta immediately; slow replies make Meta retry and send duplicates.
    threading.Thread(target=process_webhook, args=(data,), daemon=True).start()
    return jsonify({"status": "received"}), 200


def process_webhook(data):
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                field = change.get("field")
                value = change.get("value", {})
                # Other numbers (e.g. LifeDrop) can share this Meta app; only handle our own number.
                to_number = (value.get("metadata") or {}).get("phone_number_id")
                if PHONE_NUMBER_ID and to_number and to_number != PHONE_NUMBER_ID:
                    continue
                if field == "smb_message_echoes":
                    for echo in value.get("message_echoes", []):
                        handle_staff_echo(echo)
                elif field == "messages":
                    for msg in value.get("messages", []):
                        handle_client_message(msg)
                # "history", "smb_app_state_sync" and status updates are ignored.
    except Exception as e:
        print(f"[ERROR in process_webhook]: {e}")


@app.route("/infobip/webhook", methods=["POST"])
def receive_infobip_webhook():
    if not infobip.webhook_key_ok(request.args.get("key")):
        return "Forbidden", 403
    data = request.get_json(silent=True) or {}
    threading.Thread(target=process_infobip_webhook, args=(data,), daemon=True).start()
    return jsonify({"status": "received"}), 200


def process_infobip_webhook(data):
    try:
        client_messages, staff_echoes = infobip.split_webhook(data)
        for echo in staff_echoes:
            handle_staff_echo(echo)
        for msg in client_messages:
            handle_client_message(msg)
    except Exception as e:
        print(f"[ERROR in process_infobip_webhook]: {e}")


def handle_staff_echo(echo):
    """A staff member sent a message from the WhatsApp Business app (coexistence)."""
    client = echo.get("to")
    if not client:
        return
    raw_text = (echo.get("text") or {}).get("body", "").strip()
    text = raw_text.lower()
    log_message(client, "counselor", raw_text)
    with lock_for(client):
        session = load_session(client) or new_session(client)
        if text in BOT_RESUME_COMMANDS:
            # Next client message goes to the bot again (returning clients skip the questions already answered).
            fresh = new_session(client)
            store_session(fresh)
            print(f"[handover] {client} returned to bot by staff")
            return
        if session.get("mode") != "human":
            hand_to_human(session, status="taken_over_by_staff")
            save_intake(session)
            print(f"[handover] {client} taken over by staff")
        # Every counselor message keeps the chat paused, so the bot never talks over a counselor.
        store_session(session)


STOP_WORDS = {"stop", "unsubscribe", "arrêter", "arreter", "arrête", "arrete", "désabonner", "desabonner"}


def start_new_conversation(phone):
    """A fresh intake. Returning clients keep their profile, so they aren't asked the same questions again."""
    session = new_session(phone)
    contact = load_contact(phone)
    if contact and contact.get("name") and contact.get("consent"):
        for field in PROFILE_FIELDS:
            if contact.get(field):
                session["data"][field] = contact[field]
        session["returning"] = True
    return session


def handle_client_message(msg):
    sender_id = msg.get("from")
    if not sender_id or already_seen(msg.get("id")):
        return

    msg_type = msg.get("type")
    user_input = ""
    button_id = ""
    if msg_type == "text":
        user_input = msg.get("text", {}).get("body", "").strip()
    elif msg_type == "interactive":
        interactive = msg.get("interactive", {})
        kind = interactive.get("type")
        if kind in ("button_reply", "list_reply"):
            button_id = interactive[kind]["id"]
            user_input = interactive[kind]["title"]
    log_message(sender_id, "client", user_input or f"[{msg_type}]")

    with lock_for(sender_id):
        session = load_session(sender_id)
        low = user_input.strip().strip(".!").lower()

        if low in STOP_WORDS:
            save_contact(sender_id, opted_out="yes", opted_out_at=now_iso())
            if session:
                say(session, "opt_out_ack")
            else:
                send_text(sender_id, MESSAGES["opt_out_ack"]["en"] + "\n\n" + MESSAGES["opt_out_ack"]["fr"])
            return

        if session and session.get("mode") == "human":
            last = session.get("updated_at") or session.get("started_at")
            try:
                age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() / 86400
            except Exception:
                age_days = 0
            if age_days < HUMAN_MODE_RESET_DAYS:
                # A counselor is handling this chat in the WhatsApp Business app; the bot (and AI) stay off.
                store_session(session)
                return
            session = None

        if session is None or low in CLIENT_RESTART_WORDS or session.get("step") is None:
            # A new conversation (also after a counselor sent #bot): returning clients keep their profile.
            session = start_new_conversation(sender_id)

        if msg_type not in ("text", "interactive"):
            say(session, "typed_only")
            store_session(session)
            return

        mark_as_read(msg.get("id"))
        if low in DELETE_WORDS:
            # Promised in the privacy policy (/privacy#data-deletion); a counselor deletes the records.
            say(session, "delete_ack")
            hand_to_human(session, status="DELETION_REQUESTED")
            store_session(session)
            save_intake(session)
            return
        try:
            if session["step"] is None and first_message_is_urgent(user_input):
                # Don't make someone in danger pick a language first: answer in both, then a counselor takes over.
                session["data"]["warning_signs"] = f"Reported: {user_input[:200]}"
                send_text(session["phone"], MESSAGES["urgent"]["en"] + "\n\n— — —\n\n" + MESSAGES["urgent"]["fr"])
                hand_to_human(session, status="URGENT")
            elif session["step"] is None and session.get("returning"):
                say(session, "welcome_back")
                next_profile_step(session)
            elif session["step"] is None:
                go(session, "LANG")
            elif not handle_global(session, user_input, button_id):
                handle_answer(session, user_input, button_id)
        except Exception as e:
            print(f"[ERROR in flow]: {e}")
        store_session(session)
        save_intake(session)
        if session.get("mode") == "human" and not session.get("summarized"):
            session["summarized"] = True
            threading.Thread(target=summarize_intake, args=(dict(session, data=dict(session["data"])),),
                             daemon=True).start()


def summarize_intake(session):
    """A short note for counselors (e.g. to prepare pills). Saved in the Intakes row as 'summary'."""
    summary = ai.summarize(session.get("data", {}), session.get("status", ""))
    if summary:
        save_intake(session, summary=summary)


def first_message_is_urgent(text):
    """Danger words in the very first message: the AI double-checks; if the AI is off, assume urgent to be safe."""
    if not text or not has_danger_words(text):
        return False
    result = ai.classify("(first message, no question asked yet)", [], text, "en")
    return result is None or result.get("kind") == "urgent"


# After an AI answer, these typed words mean "that helped, let's continue".
QA_DONE_WORDS = {"yes", "ok", "okay", "thanks", "thank you", "thank u", "merci", "oui", "d'accord", "dacord",
                 "continue", "continuer", "got it", "compris", "c'est bon", "ça va", "ca va", "yes thanks", "oui merci"}


# Typed alone at any step (whole message), these work like the menu buttons.
MENU_WORDS = {"menu"}
LANGUAGE_WORDS = {"language", "languages", "langue", "langues"}
ENGLISH_WORDS = {"english", "anglais"}
FRENCH_WORDS = {"français", "francais", "french"}
HUMAN_WORDS = {"person", "human", "agent", "counselor", "counsellor", "conseillère", "conseillere",
               "humain", "personne"}


def handle_global(session, user_input, button_id):
    """Menu actions that work at any step. Returns True if the message was handled here."""
    low = user_input.strip().strip(".!?").lower()
    at_lang_step = session["step"] == "LANG"

    if button_id == "g_lang" or low in LANGUAGE_WORDS:
        send_buttons(session["phone"], body_text=t(session, "pick_language"),
                     buttons=buttons_for(session, "g_en", "g_fr"))
        return True

    target = None
    if button_id == "g_en" or (low in ENGLISH_WORDS and not at_lang_step):
        target = "en"
    elif button_id == "g_fr" or (low in FRENCH_WORDS and not at_lang_step):
        target = "fr"
    if target:
        session["data"]["language"] = target
        if at_lang_step:
            go(session, "CONSENT")
        else:
            say(session, "language_switched")
            ask(session)
        return True

    if button_id == "g_human" or low in HUMAN_WORDS:
        say(session, "human_handover")
        hand_to_human(session)
        return True

    if button_id == "g_restart":
        # Fresh intake, but keep the language she chose so she isn't asked again.
        fresh = new_session(session["phone"])
        fresh["data"]["language"] = lang_of(session)
        session.clear()
        session.update(fresh)
        say(session, "restarting")
        go(session, "CONSENT")
        return True

    if low in MENU_WORDS:
        send_buttons(session["phone"], body_text=t(session, "menu"),
                     buttons=buttons_for(session, "g_lang", "g_human", "g_restart"))
        return True
    return False


# =============================================================================
# UNDERSTANDING THE CLIENT'S REPLY
# =============================================================================
QUESTION_WORDS = {
    "what", "how", "why", "when", "where", "who", "which", "can", "could", "is", "are", "do", "does", "will",
    "should", "may", "qui", "que", "quoi", "comment", "pourquoi", "quand", "ou", "où", "est-ce", "puis-je",
    "combien", "quel", "quelle", "peut-on", "dois-je",
}
DANGER_WORDS = (
    "bleed", "blood", "saign", "fever", "fièvre", "fievre", "pain", "douleur", "smell", "odeur", "faint",
    "évanoui", "emergency", "urgence", "dying", "help me", "aidez",
)


def words_of(text):
    return re.findall(r"[\wÀ-ÿ'-]+", text.lower())


def looks_like_question(text):
    w = words_of(text)
    return "?" in text or (bool(w) and w[0] in QUESTION_WORDS)


def has_danger_words(text):
    low = text.lower()
    return any(d in low for d in DANGER_WORDS)


def match_option(step, text):
    """Match a typed reply to one of the step's buttons, only when it is short and unambiguous."""
    options = STEPS[step].get("options")
    if not options:
        return None
    clean = text.strip().strip(".!)").lower()
    for oid, title, _ in options:
        if clean == oid.lower() or clean == title.lower():
            return oid
    w = words_of(text)
    if not w or len(w) > 5:
        return None
    hits = [oid for oid, _, keywords in options if any(k in w or (" " in k and k in clean) for k in keywords)]
    return hits[0] if len(hits) == 1 else None


def option_title(step, oid):
    for o, title, _ in STEPS[step].get("options") or []:
        if o == oid:
            return title
    return oid


def handle_answer(session, user_input, button_id):
    step = session["step"]
    spec = STEPS[step]
    data = session["data"]
    option_ids = {o for o, _, _ in spec.get("options") or []}

    option_id = button_id if button_id in option_ids else None
    text = user_input

    # After the AI answered a side question: "yes, continue" or "another question".
    if session.get("qa"):
        low = text.strip(" .!").lower()
        if button_id == "qa_continue" or (not button_id and low in QA_DONE_WORDS):
            session.pop("qa", None)
            say(session, "back_to_question")
            ask(session)
            return
        if button_id == "qa_more":
            say(session, "qa_go_ahead")
            return

    if step in dict(PROFILE_STEPS) and not option_id and text.strip(" .!").lower() in SKIP_WORDS:
        spec["on_answer"](session, None, "Skipped")
        return

    if not option_id and text:
        option_id = match_option(step, text) or (age_option(text) if step == "AGE" else None)
        # With the AI on, every typed message that isn't an exact button choice is checked, so questions
        # are caught however they are phrased. Without the AI, only obvious questions/danger words are.
        needs_ai = (not option_id) if ai.AI_API_KEY else (
            (option_ids and not option_id) or looks_like_question(text) or has_danger_words(text))
        if needs_ai:
            result = ai.classify(
                spec["question"],
                [(o, t) for o, t, _ in spec.get("options") or []],
                text,
                data.get("language", "en"),
            )
            kind = (result or {}).get("kind")
            reply = (result or {}).get("reply", "")
            if kind in ("answer", "unclear") and not option_ids and looks_like_question(text):
                # A typed question must never be saved as her name, city, etc.
                print(f"[AI] {step}: question came back as '{kind}', not saving it as the answer")
                result, kind = None, None

            if result is None and looks_like_question(text):
                # The AI is down or busy: don't say "I didn't understand" to a real question.
                data["questions_asked"] = (data.get("questions_asked", "") + f" | {text[:200]}").strip(" |")
                say(session, "ai_unavailable")
                ask(session)
                return

            if kind == "urgent":
                data["warning_signs"] = f"Reported: {text[:200]}"
                send_text(session["phone"], reply or t(session, "urgent"))
                hand_to_human(session, status="URGENT")
                return
            if kind == "human":
                send_text(session["phone"], reply or t(session, "human_handover"))
                hand_to_human(session)
                return
            if kind == "question":
                session["ai_questions"] = session.get("ai_questions", 0) + 1
                data["questions_asked"] = (data.get("questions_asked", "") + f" | {text[:200]}").strip(" |")
                if session["ai_questions"] > AI_MAX_QUESTIONS:
                    send_text(session["phone"], (reply + "\n\n" if reply else "") + t(session, "ai_limit"))
                    hand_to_human(session)
                    return
                # Answer her question, then check it helped before going back to the intake.
                if reply:
                    send_text(session["phone"], reply)
                session["qa"] = True
                ask_buttons(session, "qa_check", ["qa_continue", "qa_more"])
                return
            if kind == "answer" and option_ids and looks_like_question(text) and not reply:
                # Safety net: a question must not be taken as "yes" to the current question.
                kind, result = "unclear", None
            if kind == "answer":
                session.pop("qa", None)
                option_id = result.get("option_id") or option_id
                text = result.get("value") or text
            if option_ids and not option_id:
                # Not an answer we understood: ask the same question again.
                say(session, "not_understood")
                ask(session)
                return

    if option_ids and not option_id:
        ask(session)
        return

    session.pop("qa", None)
    value = option_title(step, option_id) if option_id else text
    spec["on_answer"](session, option_id, value)


# =============================================================================
# INTAKE FLOW
# Each step: "ask" sends the question, "on_answer" stores the answer and moves on.
# =============================================================================
def go(session, step):
    session["step"] = step
    ask(session)


def ask(session):
    STEPS[session["step"]]["ask"](session)


def lang_of(session):
    return "fr" if (session.get("data") or {}).get("language") == "fr" else "en"


def name_of(session):
    name = (session.get("data") or {}).get("name") or "Friend"
    return DEFAULT_NAME[lang_of(session)] if name == "Friend" else name


def t(session, key, **kw):
    """The text for `key` in the client's language, with {name} filled in."""
    return MESSAGES[key][lang_of(session)].format(name=name_of(session), **kw)


def say(session, key, **kw):
    return send_text(session["phone"], t(session, key, **kw))


def buttons_for(session, *ids):
    lang = lang_of(session)
    return [{"id": i, "title": BUTTONS[i][lang]} for i in ids]


def ask_buttons(session, key, ids, prefix="", **kw):
    return send_buttons(session["phone"], body_text=prefix + t(session, key, **kw), buttons=buttons_for(session, *ids))


# ----- STAGE 0 / 1: LANGUAGE, WELCOME & CONSENT ------------------------------
def ask_lang(s):
    send_buttons(
        s["phone"],
        body_text=t(s, "lang_prompt"),
        buttons=buttons_for(s, "lang_en", "lang_fr"),
        footer_text="Aunty Queen"
    )


def on_lang(s, oid, value):
    s["data"]["language"] = "fr" if oid == "lang_fr" else "en"
    go(s, "CONSENT")


def ask_consent(s):
    ask_buttons(s, "consent", ["c_ok", "c_what"])


def on_consent(s, oid, value):
    s["data"]["consent"] = "yes"
    first = t(s, "consent_what") if oid == "c_what" else t(s, "consent_thanks")
    send_text(s["phone"], first + "\n\n" + t(s, "name_ask"))
    s["step"] = "NAME"


def ask_name(s):
    say(s, "name_ask")


def on_name(s, oid, value):
    s["data"]["name"] = value[:60] if value else "Friend"
    s["show_demo_intro"] = True
    next_profile_step(s)


# ----- A FEW DETAILS ABOUT HER (script 1.3a + gender, city, how she heard) -----
PROFILE_STEPS = [("AGE", "age"), ("GENDER", "gender"), ("CITY", "city"), ("EDUCATION", "education"),
                 ("PREGNANCIES", "pregnancies_children"), ("HEARD", "heard_from")]
SKIP_WORDS = {"skip", "passer", "pass", "next", "suivant", "non merci", "no thanks"}


def next_profile_step(s):
    """Ask the first profile question she hasn't answered yet, then move on to how we can help."""
    for step, field in PROFILE_STEPS:
        if not s["data"].get(field):
            go(s, step)
            return
    go(s, "HELP")


def intro(s):
    return t(s, "demo_intro") if s.pop("show_demo_intro", False) else ""


def save_profile(field):
    def on_answer(s, oid, value):
        s["data"][field] = (value or "Skipped")[:120]
        next_profile_step(s)
    return on_answer


AGE_RANGES = ("age_u18", "age_18_24", "age_25_34", "age_35_44", "age_45")


def ask_age(s):
    lang = lang_of(s)
    rows = [{"id": i, "title": BUTTONS[i][lang]} for i in AGE_RANGES]
    send_list(s["phone"], intro(s) + t(s, "age"), MESSAGES["heard_button"][lang], rows)


def age_option(text):
    """A typed age like "22" or "I am 22" -> its range, so she doesn't have to use the list."""
    m = re.fullmatch(r"\D{0,12}?(\d{1,2})\s*(ans|years?( old)?|yrs?)?\W*", text.strip().lower())
    if not m:
        return None
    age = int(m.group(1))
    return ("age_u18" if age < 18 else "age_18_24" if age < 25 else "age_25_34" if age < 35
            else "age_35_44" if age < 45 else "age_45")


def ask_gender(s):
    ask_buttons(s, "gender", ["gen_woman", "gen_man", "gen_other"], prefix=intro(s))


def ask_city(s):
    send_text(s["phone"], intro(s) + t(s, "city"))


def ask_education(s):
    ask_buttons(s, "education", ["edu_primary", "edu_secondary", "edu_higher"], prefix=intro(s))


def ask_pregnancies(s):
    send_text(s["phone"], intro(s) + t(s, "pregnancies"))


def ask_heard(s):
    lang = lang_of(s)
    rows = [{"id": i, "title": BUTTONS[i][lang]} for i in
            ("heard_friend", "heard_social", "heard_radio", "heard_web", "heard_health", "heard_other")]
    send_list(s["phone"], intro(s) + t(s, "heard"), MESSAGES["heard_button"][lang], rows)


def ask_help(s):
    if s.get("help_seen"):
        key = "help_again"
    elif s.get("returning"):
        key = "help_returning"
    else:
        key = "help_first"
    say(s, key)
    s["help_seen"] = True


def on_help(s, oid, value):
    s["data"]["category"] = value
    if oid == "1":
        go(s, "PILLS_OFFER")
    elif oid == "2":
        go(s, "TRIAGE")
    elif oid == "3":
        say(s, "contraception_info")
        go(s, "FOLLOWUP")
    else:
        say(s, "help_other")
        hand_to_human(s)


def ask_pills_offer(s):
    ask_buttons(s, "pills_offer", ["pills_yes", "pills_no"])


def on_pills_offer(s, oid, value):
    if oid == "pills_no":
        go(s, "HELP")
    else:
        go(s, "CONFIRMATION")


# ----- STAGE 2: UNDERSTANDING HER SITUATION ----------------------------------
def ask_confirmation(s):
    ask_buttons(s, "confirmation", ["conf_test", "conf_scan", "conf_missed"])


def on_confirmation(s, oid, value):
    s["data"]["confirmation_method"] = value
    go(s, "LMP")


def ask_lmp(s):
    say(s, "lmp_scan" if s["data"].get("confirmation_method") == "Ultrasound (scan)" else "lmp")


def on_lmp(s, oid, value):
    s["data"]["lmp"] = value
    go(s, "PREFERENCE")


def ask_preference(s):
    ask_buttons(s, "preference", ["pref_pills", "pref_mva", "pref_both"])


def on_preference(s, oid, value):
    s["data"]["preference"] = value
    go(s, "HEALTH")


def ask_health(s):
    ask_buttons(s, "health", ["health_no", "health_yes"])


def on_health(s, oid, value):
    if oid == "health_yes":
        send_text(s["phone"], t(s, "health_yes") + "\n\n" + t(s, "health_details"))
        s["step"] = "HEALTH_DETAILS"
    else:
        s["data"]["health_issues"] = "None reported"
        go(s, "SUPPORT")


def ask_health_details(s):
    say(s, "health_details")


def on_health_details(s, oid, value):
    s["data"]["health_issues"] = value
    go(s, "SUPPORT")


def ask_support(s):
    ask_buttons(s, "support", ["supp_yes", "supp_no"])


def on_support(s, oid, value):
    s["data"]["support_person"] = value
    go(s, "DECISION")


def ask_decision(s):
    alone = s["data"].get("support_person") == "No, I am alone"
    ask_buttons(s, "decision", ["dec_continue", "dec_questions"], prefix=t(s, "not_alone") if alone else "")


def on_decision(s, oid, value):
    if oid == "dec_questions":
        s["data"]["decision"] = "Has questions"
        say(s, "decision_questions")
        hand_to_human(s)
    elif s["data"].get("preference") == "MVA in a clinic":
        s["data"]["decision"] = "Continue (MVA)"
        say(s, "decision_mva")
        hand_to_human(s)
    else:
        s["data"]["decision"] = "Continue"
        say(s, "methods")
        go(s, "PLAN")


# ----- STAGE 3 / 4: BEFORE THE ABORTION, USING THE PILLS ---------------------
def ask_plan(s):
    ask_buttons(s, "plan", ["plan_ready", "plan_ask"])


def on_plan(s, oid, value):
    if oid == "plan_ask":
        # The AI answers typed questions; this button means she wants to write one.
        say(s, "plan_ask")
        s["step"] = "PLAN_QUESTION"
    else:
        go(s, "METHOD")


def ask_plan_question(s):
    say(s, "plan_question_reask")


def on_plan_question(s, oid, value):
    # Questions are answered by the AI first. If the AI is off, a counselor takes the question.
    if looks_like_question(value):
        say(s, "plan_question_human")
        s["data"]["questions_asked"] = value[:200]
        hand_to_human(s)
    else:
        go(s, "METHOD")


def ask_method(s):
    ask_buttons(s, "method", ["m_miso_only", "m_combo"])


def on_method(s, oid, value):
    if oid == "m_combo":
        s["data"]["pill_choice"] = "Mifepristone + Misoprostol"
        steps = t(s, "steps_combo")
    else:
        s["data"]["pill_choice"] = "Misoprostol alone"
        steps = t(s, "steps_miso")
    send_text(s["phone"], steps)
    send_text(s["phone"], t(s, "good_to_know") + "\n\n" + t(s, "understanding"))
    s["step"] = "UNDERSTANDING"


def ask_understanding(s):
    say(s, "understanding")


def on_understanding(s, oid, value):
    s["data"]["understanding"] = value
    s["warning_intro_done"] = False
    go(s, "WARN_CHECK")


# ----- STAGE 5: SIGNS OF COMPLICATION ----------------------------------------
def ask_warn_check(s):
    intro = "warning_again" if s.get("warning_intro_done") else "warning_intro"
    s["warning_intro_done"] = True
    ask_buttons(s, "warning_signs", ["warn_clear", "warn_repeat"], prefix=t(s, intro) + "\n\n")


def on_warn_check(s, oid, value):
    if oid == "warn_repeat":
        ask(s)
    else:
        go(s, "CONTRACEPTION")


# ----- STAGE 6: AFTER THE ABORTION & CONTRACEPTION ---------------------------
def ask_contraception(s):
    ask_buttons(s, "after", ["contra_yes", "contra_no"])


def on_contraception(s, oid, value):
    s["data"]["contraception_info"] = value
    if oid == "contra_yes":
        say(s, "contraception_info")
    go(s, "FOLLOWUP")


# ----- STAGE 7: CLOSING AND FOLLOW-UP ----------------------------------------
def ask_followup(s):
    say(s, "followup")


def on_followup(s, oid, value):
    s["data"]["followup_time"] = value
    say(s, "closing")
    hand_to_human(s, status="completed")


# ----- Option 2: already used the pills --------------------------------------
def ask_triage(s):
    ask_buttons(s, "triage", ["warn_report_yes", "warn_report_no"])


def on_triage(s, oid, value):
    if oid == "warn_report_yes":
        s["data"]["warning_signs"] = "YES"
        say(s, "urgent")
        hand_to_human(s, status="URGENT")
    else:
        s["data"]["warning_signs"] = "No"
        say(s, "triage_no")
        hand_to_human(s)


YES = ["yes", "oui", "ok", "yeah", "yep", "sure", "d'accord"]
NO = ["no", "non", "nope", "nah"]

# options: (button id, title, typed keywords that pick it)
STEPS = {
    "AGE": {"ask": ask_age, "on_answer": save_profile("age"), "question": "What is your age range?",
            "options": [("age_u18", "Under 18", ["under", "moins"]),
                        ("age_18_24", "18-24", ["18-24"]),
                        ("age_25_34", "25-34", ["25-34"]),
                        ("age_35_44", "35-44", ["35-44"]),
                        ("age_45", "45 or older", ["45+", "older", "plus"])]},
    "GENDER": {"ask": ask_gender, "on_answer": save_profile("gender"), "question": "How do you identify: woman, man or other?",
               "options": [("gen_woman", "Woman", ["woman", "female", "femme", "f", "girl", "fille"]),
                           ("gen_man", "Man", ["man", "male", "homme", "m", "boy", "garçon"]),
                           ("gen_other", "Other / rather not say", ["other", "autre", "non-binary", "prefer"])]},
    "CITY": {"ask": ask_city, "on_answer": save_profile("city"), "question": "Which town or city do you live in?"},
    "EDUCATION": {"ask": ask_education, "on_answer": save_profile("education"),
                  "question": "Highest level of school completed: none/primary, secondary, or university?",
                  "options": [("edu_primary", "None or primary", ["none", "primary", "primaire", "aucun", "cep"]),
                              ("edu_secondary", "Secondary", ["secondary", "secondaire", "lycée", "lycee", "college", "collège", "bac", "gce"]),
                              ("edu_higher", "University / higher", ["university", "université", "universite", "fac", "higher", "supérieur", "degree", "licence"])]},
    "PREGNANCIES": {"ask": ask_pregnancies, "on_answer": save_profile("pregnancies_children"),
                    "question": "How many pregnancies and how many children?"},
    "HEARD": {"ask": ask_heard, "on_answer": save_profile("heard_from"), "question": "How did you hear about Aunty Queen?",
              "options": [("heard_friend", "Friend or family", ["friend", "family", "ami", "amie", "famille", "sister", "soeur"]),
                          ("heard_social", "Social media", ["social", "facebook", "tiktok", "instagram", "whatsapp", "réseaux", "reseaux"]),
                          ("heard_radio", "Radio or TV", ["radio", "tv", "télé", "tele", "television"]),
                          ("heard_web", "Website", ["website", "site", "internet", "google"]),
                          ("heard_health", "Health worker or clinic", ["clinic", "clinique", "hospital", "hôpital", "nurse", "doctor", "médecin", "health"]),
                          ("heard_other", "Other", ["other", "autre"])]},
    "LANG": {"ask": ask_lang, "on_answer": on_lang, "question": "Choose a language: English or French",
             "options": [("lang_en", "English", ["english", "anglais", "en"]),
                         ("lang_fr", "Français", ["français", "francais", "french", "fr"])]},
    "CONSENT": {"ask": ask_consent, "on_answer": on_consent, "question": "Is it OK if we ask a few personal questions?",
                "options": [("c_ok", "Yes, that is OK", YES), ("c_what", "What will you ask?", ["what", "quoi"])]},
    "NAME": {"ask": ask_name, "on_answer": on_name, "question": "What name would you like us to call you?"},
    "HELP": {"ask": ask_help, "on_answer": on_help,
             "question": "How can we support you? 1 safe abortion with pills, 2 already used pills, 3 contraception, 4 something else",
             "options": [("1", "Information about safe abortion with pills", ["1", "abortion", "avortement"]),
                         ("2", "Already used the pills", ["2", "already", "déjà"]),
                         ("3", "Information about contraception", ["3", "contraception"]),
                         ("4", "Something else", ["4"])]},
    "PILLS_OFFER": {"ask": ask_pills_offer, "on_answer": on_pills_offer,
                    "question": "Would you like information about safe abortion with pills?",
                    "options": [("pills_yes", "Yes", YES), ("pills_no", "No", NO)]},
    "CONFIRMATION": {"ask": ask_confirmation, "on_answer": on_confirmation,
                     "question": "How was the pregnancy confirmed?",
                     "options": [("conf_test", "Pregnancy test", ["test"]),
                                 ("conf_scan", "Ultrasound (scan)", ["scan", "ultrasound", "echo", "échographie"]),
                                 ("conf_missed", "Missed period only", ["missed", "late", "retard"])]},
    "LMP": {"ask": ask_lmp, "on_answer": on_lmp, "question": "What was the first day of the last menstrual period?"},
    "PREFERENCE": {"ask": ask_preference, "on_answer": on_preference,
                   "question": "Do you prefer pills at home, MVA in a clinic, or hear about both?",
                   "options": [("pref_pills", "Pills", ["pills", "pill", "pilules"]),
                               ("pref_mva", "MVA in a clinic", ["mva", "clinic", "clinique", "amiu"]),
                               ("pref_both", "Hear about both", ["both", "deux"])]},
    "HEALTH": {"ask": ask_health, "on_answer": on_health,
               "question": "Do you have health problems or allergies, take medication, or have an IUD?",
               "options": [("health_no", "No to all", NO + ["none", "rien", "aucun"]),
                           ("health_yes", "I have some", YES + ["some"])]},
    "HEALTH_DETAILS": {"ask": ask_health_details, "on_answer": on_health_details,
                       "question": "Which health condition, medication or IUD do you have?"},
    "SUPPORT": {"ask": ask_support, "on_answer": on_support,
                "question": "Is there someone who can be with you and someone you can talk to?",
                "options": [("supp_yes", "Yes, I have support", YES), ("supp_no", "No, I am alone", NO + ["alone", "seule"])]},
    "DECISION": {"ask": ask_decision, "on_answer": on_decision,
                 "question": "Are you comfortable continuing to information on what is needed?",
                 "options": [("dec_continue", "Yes, continue", YES + ["continue", "continuer"]),
                             ("dec_questions", "I have questions", ["questions", "question"])]},
    "PLAN": {"ask": ask_plan, "on_answer": on_plan, "question": "Do you have any questions so far, or are you ready for the steps?",
             "options": [("plan_ready", "Ready for steps", YES + ["ready", "prête", "prete"]),
                         ("plan_ask", "I have a question", ["question"])]},
    "PLAN_QUESTION": {"ask": ask_plan_question, "on_answer": on_plan_question,
                      "question": "Type your question, or type ready to continue"},
    "METHOD": {"ask": ask_method, "on_answer": on_method, "question": "Which pills will you use: misoprostol alone or mifepristone + misoprostol?",
               "options": [("m_miso_only", "Misoprostol alone", ["alone", "seul", "only"]),
                           ("m_combo", "Mife + Misoprostol", ["mife", "mifepristone", "both", "combo"])]},
    "UNDERSTANDING": {"ask": ask_understanding, "on_answer": on_understanding,
                      "question": "In your own words, how are the pills taken? Any doubts?"},
    "WARN_CHECK": {"ask": ask_warn_check, "on_answer": on_warn_check, "question": "Are the 4 warning signs clear to you?",
                   "options": [("warn_clear", "Yes, all clear", YES + ["clear", "clair"]),
                               ("warn_repeat", "Please repeat", ["repeat", "again", "répéter", "repeter"])]},
    "CONTRACEPTION": {"ask": ask_contraception, "on_answer": on_contraception,
                      "question": "Would you like information about contraception?",
                      "options": [("contra_yes", "Yes", YES), ("contra_no", "No, thank you", NO)]},
    "FOLLOWUP": {"ask": ask_followup, "on_answer": on_followup,
                 "question": "Any other concern? Would you like us to check in later, and which day and time is safe?"},
    "TRIAGE": {"ask": ask_triage, "on_answer": on_triage, "question": "Are you experiencing any of the 4 warning signs right now?",
               "options": [("warn_report_yes", "Yes, I have them", YES), ("warn_report_no", "No, I do not", NO)]},
}


# =============================================================================
# DASHBOARD (counselors only; password = DASHBOARD_KEY)
# =============================================================================
DASHBOARD_KEY = os.environ.get("DASHBOARD_KEY", "")
BROADCAST_TEMPLATE = os.environ.get("BROADCAST_TEMPLATE", "")
COOKIE = "aq_dash"


def dashboard_token():
    return hmac.new(DASHBOARD_KEY.encode(), b"aunty-queen-dashboard", hashlib.sha256).hexdigest()


def dashboard_ok():
    return bool(DASHBOARD_KEY) and hmac.compare_digest(request.cookies.get(COOKIE, ""), dashboard_token())


def html_response(body, status=200):
    return body, status, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store",
                          "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer"}


@app.route("/dashboard/login", methods=["POST"])
def dashboard_login():
    if not DASHBOARD_KEY:
        return html_response(dashboard.login_page("The dashboard is off: set DASHBOARD_KEY in Render."), 503)
    if not hmac.compare_digest(request.form.get("key", ""), DASHBOARD_KEY):
        return html_response(dashboard.login_page("Wrong password."), 403)
    resp = make_response(redirect("/dashboard"))
    resp.set_cookie(COOKIE, dashboard_token(), max_age=12 * 3600, httponly=True, secure=True, samesite="Strict")
    return resp


@app.route("/dashboard/logout")
def dashboard_logout():
    resp = make_response(redirect("/dashboard"))
    resp.delete_cookie(COOKIE)
    return resp


def dashboard_data():
    data = sheet_call("dashboard_data", {}) or {}
    return data.get("intakes", []), data.get("contacts", []), data.get("imported", [])


@app.route("/dashboard")
def dashboard_home():
    if not dashboard_ok():
        return html_response(dashboard.login_page())
    if not GOOGLE_SHEET_WEBHOOK_URL:
        return html_response(dashboard.page("Dashboard", "<main><p class='msg'>Connect the Google Sheet first "
                                            "(GOOGLE_SHEET_WEBHOOK_URL and SHEET_SECRET in Render).</p></main>"))
    intakes, contacts_rows, imported = dashboard_data()
    stats = dashboard.compute_stats(intakes, contacts_rows, imported)
    audience = dashboard.broadcast_audience(contacts_rows, imported)
    return html_response(dashboard.dashboard_page(stats, len(audience), request.args.get("msg", ""), BROADCAST_TEMPLATE))


@app.route("/dashboard/chat")
def dashboard_chat():
    if not dashboard_ok():
        return redirect("/dashboard")
    phone = re.sub(r"\D", "", request.args.get("phone", ""))
    messages = (sheet_call("messages_for", {"phone": phone}) or {}).get("messages", [])
    return html_response(dashboard.chat_page(phone, messages, load_contact(phone)))


@app.route("/dashboard/import", methods=["POST"])
def dashboard_import():
    if not dashboard_ok():
        return redirect("/dashboard")
    f = request.files.get("file")
    try:
        rows = dashboard.read_upload(f.filename if f else "", f.read() if f else b"")
    except Exception as e:
        return redirect("/dashboard?msg=" + requests.utils.quote(f"Could not read the file: {e}"))
    batch = f"{now_iso()[:16]} {f.filename}"[:80]
    for r in rows:
        r.update({"import_batch": batch, "imported_at": now_iso()})
    for i in range(0, len(rows), 200):
        sheet_call("import_rows", {"rows": rows[i:i + 200]})
    return redirect("/dashboard?msg=" + requests.utils.quote(f"Imported {len(rows)} rows from {f.filename}."))


def run_broadcast(phones, template, language):
    sent = 0
    for phone in phones:
        r = send_template(phone, template, language)
        if r is not None and getattr(r, "status_code", 500) < 300:
            sent += 1
            save_contact(phone, last_broadcast_at=now_iso(), last_broadcast_template=template)
        time.sleep(0.3)
    print(f"[broadcast] {template}: sent {sent} of {len(phones)}")


@app.route("/dashboard/broadcast", methods=["POST"])
def dashboard_broadcast():
    if not dashboard_ok():
        return redirect("/dashboard")
    template = re.sub(r"[^a-z0-9_]", "", request.form.get("template", "").strip().lower())
    language = "fr" if request.form.get("language") == "fr" else "en"
    _, contacts_rows, imported = dashboard_data()
    phones = dashboard.broadcast_audience(contacts_rows, imported)
    if not template:
        return redirect("/dashboard?msg=" + requests.utils.quote("Enter the approved template name."))
    if request.form.get("confirm", "").strip().upper() != f"SEND {len(phones)}":
        return redirect("/dashboard?msg=" + requests.utils.quote(f"Not sent. Type exactly: SEND {len(phones)}"))
    threading.Thread(target=run_broadcast, args=(phones, template, language), daemon=True).start()
    return redirect("/dashboard?msg=" + requests.utils.quote(
        f"Broadcast started to {len(phones)} people. Replies will come into the bot as normal."))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
