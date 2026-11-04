import hashlib
import hmac
import os
import re
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timezone

import requests
import ai
import infobip
from messages import MESSAGES, BUTTONS, DEFAULT_NAME
from flask import Flask, request, jsonify

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


def send_text(recipient_id, text_body):
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


def mark_as_read(message_id):
    if USE_INFOBIP:
        return infobip.mark_as_read(message_id)
    send_meta_request({"messaging_product": "whatsapp", "status": "read", "message_id": message_id})


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
    text = (echo.get("text") or {}).get("body", "").strip().lower()
    with lock_for(client):
        session = load_session(client) or new_session(client)
        if text in BOT_RESUME_COMMANDS:
            # Next client message starts a fresh intake with the bot.
            fresh = new_session(client)
            store_session(fresh)
            print(f"[handover] {client} returned to bot by staff")
            return
        if session.get("mode") != "human":
            hand_to_human(session, status="taken_over_by_staff")
            save_intake(session)
            print(f"[handover] {client} taken over by staff")
        store_session(session)


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
        if interactive.get("type") == "button_reply":
            button_id = interactive["button_reply"]["id"]
            user_input = interactive["button_reply"]["title"]

    with lock_for(sender_id):
        session = load_session(sender_id)

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

        if session is None or user_input.lower() in CLIENT_RESTART_WORDS:
            session = new_session(sender_id)

        if msg_type not in ("text", "interactive"):
            say(session, "typed_only")
            store_session(session)
            return

        mark_as_read(msg.get("id"))
        if user_input.strip().lower() in DELETE_WORDS:
            # Promised in the privacy policy (/privacy#data-deletion); a counselor deletes the records.
            say(session, "delete_ack")
            hand_to_human(session, status="DELETION_REQUESTED")
            store_session(session)
            save_intake(session)
            return
        try:
            if session["step"] is None:
                go(session, "LANG")
            else:
                handle_answer(session, user_input, button_id)
        except Exception as e:
            print(f"[ERROR in flow]: {e}")
        store_session(session)
        save_intake(session)


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

    if not option_id and text:
        option_id = match_option(step, text)
        needs_ai = (option_ids and not option_id) or looks_like_question(text) or has_danger_words(text)
        if needs_ai:
            result = ai.classify(
                spec["question"],
                [(o, t) for o, t, _ in spec.get("options") or []],
                text,
                data.get("language", "en"),
            )
            kind = (result or {}).get("kind")
            reply = (result or {}).get("reply", "")

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
                if reply:
                    send_text(session["phone"], reply)
                if session["ai_questions"] > AI_MAX_QUESTIONS:
                    say(session, "ai_limit")
                    hand_to_human(session)
                    return
                say(session, "back_to_question")
                ask(session)
                return
            if kind == "answer":
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
    go(s, "HELP")


def ask_help(s):
    say(s, "help_again" if s.get("help_seen") else "help_first")
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
