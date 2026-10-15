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
            send_text(sender_id, "Sorry, our assistant can only read typed messages. Please type your answer, "
                                 "or wait and a counselor will reply to you here.")
            store_session(session)
            return

        mark_as_read(msg.get("id"))
        if user_input.strip().lower() in DELETE_WORDS:
            # Promised in the privacy policy (/privacy#data-deletion); a counselor deletes the records.
            send_text(sender_id, "We have received your request. A counselor will delete your records and confirm here.")
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
                send_text(session["phone"], reply or URGENT_TEXT)
                hand_to_human(session, status="URGENT")
                return
            if kind == "human":
                send_text(session["phone"], reply or "Thank you. A counselor will reply to you here directly.")
                hand_to_human(session)
                return
            if kind == "question":
                session["ai_questions"] = session.get("ai_questions", 0) + 1
                data["questions_asked"] = (data.get("questions_asked", "") + f" | {text[:200]}").strip(" |")
                if reply:
                    send_text(session["phone"], reply)
                if session["ai_questions"] > AI_MAX_QUESTIONS:
                    send_text(session["phone"], "A counselor will continue with you here directly.")
                    hand_to_human(session)
                    return
                send_text(session["phone"], "To continue, here is where we were:")
                ask(session)
                return
            if kind == "answer":
                option_id = result.get("option_id") or option_id
                text = result.get("value") or text
            if option_ids and not option_id:
                # Not an answer we understood: ask the same question again.
                send_text(session["phone"], "Sorry, I did not understand. Please choose one of the options below.")
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


def name_of(session):
    return session["data"].get("name", "Friend")


URGENT_TEXT = (
    "🚨 *What you describe is one of the signs that needs medical care.*\n\n"
    "Please go to the nearest health facility now. The treatment is the same as for a miscarriage, "
    "and a woman can say she had a miscarriage. Message us when you can; we are here."
)


# ----- STAGE 0 / 1: LANGUAGE, WELCOME & CONSENT ------------------------------
def ask_lang(s):
    send_buttons(
        s["phone"],
        body_text="Hello, and welcome to Aunty Queen Hotline.\nPlease select your language / Choisissez votre langue :",
        buttons=[{"id": "lang_en", "title": "English"}, {"id": "lang_fr", "title": "Français"}],
        footer_text="Aunty Queen Hotline"
    )


def on_lang(s, oid, value):
    s["data"]["language"] = "fr" if oid == "lang_fr" else "en"
    go(s, "CONSENT")


def ask_consent(s):
    send_buttons(
        s["phone"],
        body_text=(
            "Hello, and welcome to Aunty Queen Hotline.\n"
            "We share general information on sexual and reproductive health, including safe abortion information based on World Health Organization guidelines.\n\n"
            "🔒 *Confidentiality and chat safety:*\n"
            "Everything shared in this chat is kept confidential. It is used only for our own records.\n"
            "To keep this chat private on the phone, many women turn on disappearing messages or delete the chat when we finish.\n\n"
            "To support you well, we will need to ask a few personal questions. Would that be OK?"
        ),
        buttons=[{"id": "c_ok", "title": "Yes, that is OK"}, {"id": "c_what", "title": "What will you ask?"}]
    )


def on_consent(s, oid, value):
    if oid == "c_what":
        # 1.3a What we ask
        send_text(s["phone"], (
            "*What we ask:*\n"
            "We ask about: age, date of last period, education, number of pregnancies and children, "
            "reason for reaching out, and whether someone is supporting you.\n\n"
            "Any question can be skipped."
        ))
    else:
        send_text(s["phone"], "Thank you.")
    s["data"]["consent"] = "yes"
    go(s, "NAME")


def ask_name(s):
    send_text(s["phone"], "What name would you like us to call you?")


def on_name(s, oid, value):
    s["data"]["name"] = value[:60] if value else "Friend"
    go(s, "HELP")


def ask_help(s):
    send_text(s["phone"], (
        f"Thank you, {name_of(s)}.\n\n"
        "How can we support you today? Please reply with the number:\n"
        "1. Information about safe abortion with pills\n"
        "2. I have already used the pills and have questions\n"
        "3. Information about contraception\n"
        "4. Something else"
    ))


def on_help(s, oid, value):
    name = name_of(s)
    s["data"]["category"] = value
    if oid == "1":
        go(s, "PILLS_OFFER")
    elif oid == "2":
        go(s, "TRIAGE")
    elif oid == "3":
        send_stage_6_3_contraception(s["phone"])
        go(s, "FOLLOWUP")
    else:
        send_text(s["phone"], f"Please explain in your own words how we can assist you, {name}. A counselor will reply to you directly.")
        hand_to_human(s)


def ask_pills_offer(s):
    # 1.5 What the hotline offers
    send_buttons(
        s["phone"],
        body_text=(
            f"We will do our best to support you, {name_of(s)}.\n\n"
            "Aunty Queen shares scientific information about safe self-managed abortion with pills, "
            "for pregnancies up to 12 weeks. We can also give information about manual vacuum aspiration (MVA), which is done in a clinic.\n\n"
            "An abortion with pills causes the same process as a miscarriage.\n\n"
            "Would you like information about safe abortion with pills?"
        ),
        buttons=[{"id": "pills_yes", "title": "Yes"}, {"id": "pills_no", "title": "No"}]
    )


def on_pills_offer(s, oid, value):
    if oid == "pills_no":
        send_text(s["phone"], f"No problem, {name_of(s)}.")
        go(s, "HELP")
    else:
        go(s, "CONFIRMATION")


# ----- STAGE 2: UNDERSTANDING HER SITUATION ----------------------------------
def ask_confirmation(s):
    # 2.1 How the pregnancy was confirmed
    send_buttons(
        s["phone"],
        body_text=f"Can you tell us how the pregnancy was confirmed, {name_of(s)}?",
        buttons=[
            {"id": "conf_test", "title": "Pregnancy test"},
            {"id": "conf_scan", "title": "Ultrasound (scan)"},
            {"id": "conf_missed", "title": "Missed period only"}
        ]
    )


def on_confirmation(s, oid, value):
    s["data"]["confirmation_method"] = value
    go(s, "LMP")


def ask_lmp(s):
    if s["data"].get("confirmation_method") == "Ultrasound (scan)":
        send_text(s["phone"], "What did the scan result say, and how many weeks? Also, what was the first day of your last menstrual period (an approximate date is fine)?")
    else:
        # 2.2 Length of pregnancy
        send_text(s["phone"], "What was the first day of the last menstrual period? An approximate date is fine.")


def on_lmp(s, oid, value):
    s["data"]["lmp"] = value
    go(s, "PREFERENCE")


def ask_preference(s):
    # 2.3 Preference: pills or clinic procedure
    send_buttons(
        s["phone"],
        body_text=(
            "Some women prefer abortion with pills at home. Others prefer MVA, a short procedure in a clinic. "
            f"Do you already know which one you prefer, {name_of(s)}?"
        ),
        buttons=[
            {"id": "pref_pills", "title": "Pills"},
            {"id": "pref_mva", "title": "MVA in a clinic"},
            {"id": "pref_both", "title": "Hear about both"}
        ]
    )


def on_preference(s, oid, value):
    s["data"]["preference"] = value
    go(s, "HEALTH")


def ask_health(s):
    # 2.4 Health questions
    send_buttons(
        s["phone"],
        body_text=(
            f"Can we ask a few health questions, {name_of(s)}?\n\n"
            "- Do you have any health problems or allergies?\n"
            "- Are you taking any medication?\n"
            "- Do you have an IUD (coil)?"
        ),
        buttons=[{"id": "health_no", "title": "No to all"}, {"id": "health_yes", "title": "I have some"}]
    )


def on_health(s, oid, value):
    if oid == "health_yes":
        # 2.4a If health problem reported
        send_text(s["phone"], (
            "Thank you for telling us. An early abortion with pills is safer than continuing a pregnancy and giving birth, "
            "and for some health conditions pregnancy can make the condition worse.\n\n"
            "Women with health problems can still use the pills. They are advised to have someone with them and to be near medical care in case of a complication."
        ))
        go(s, "HEALTH_DETAILS")
    else:
        s["data"]["health_issues"] = "None reported"
        go(s, "SUPPORT")


def ask_health_details(s):
    send_text(s["phone"], "Please briefly mention any specific condition, medication, or if you have an IUD:")


def on_health_details(s, oid, value):
    s["data"]["health_issues"] = value
    go(s, "SUPPORT")


def ask_support(s):
    send_buttons(
        s["phone"],
        body_text=(
            "The risk of complications is very low, but it can help to have someone for emotional support.\n\n"
            f"Is there someone who can be with you during the abortion, and someone you can talk to about it, {name_of(s)}?"
        ),
        buttons=[{"id": "supp_yes", "title": "Yes, I have support"}, {"id": "supp_no", "title": "No, I am alone"}]
    )


def on_support(s, oid, value):
    s["data"]["support_person"] = value
    go(s, "DECISION")


def ask_decision(s):
    # 2.6 Her decision
    send_buttons(
        s["phone"],
        body_text=(
            f"Can we ask about your decision, {name_of(s)}? It is important that this choice is yours, made without pressure from anyone.\n\n"
            "You are the only person who can judge your situation and make the best choice for your life.\n\n"
            "Are you comfortable continuing to information on what is needed?"
        ),
        buttons=[{"id": "dec_continue", "title": "Yes, continue"}, {"id": "dec_questions", "title": "I have questions"}]
    )


def on_decision(s, oid, value):
    name = name_of(s)
    if oid == "dec_questions":
        s["data"]["decision"] = "Has questions"
        send_text(s["phone"], f"Of course, {name}. Please type your questions here and a counselor will reply to you directly.")
        hand_to_human(s)
    elif s["data"].get("preference") == "MVA in a clinic":
        s["data"]["decision"] = "Continue (MVA)"
        send_text(s["phone"], f"Thank you, {name}. A counselor will share information about MVA and clinics with you here.")
        hand_to_human(s)
    else:
        s["data"]["decision"] = "Continue"
        # 3.1 & 3.2 What is needed
        send_text(s["phone"], (
            "Research shows two effective methods:\n"
            "1. *Mifepristone with misoprostol*: 1 mifepristone tablet (200 mg) and 4 misoprostol tablets (200 mcg each)\n"
            "2. *Misoprostol alone*: 12 misoprostol tablets (200 mcg each)\n\n"
            "Where to get pills: A counselor can discuss safe access options confidentially."
        ))
        go(s, "PLAN")


# ----- STAGE 3 / 4: BEFORE THE ABORTION, USING THE PILLS ---------------------
def ask_plan(s):
    # 3.3 & 3.4 Planning and readiness
    send_buttons(
        s["phone"],
        body_text=(
            "While getting the pills, you can start making a plan for the day:\n"
            "- Someone to give emotional support\n"
            "- Childcare and other tasks arranged\n"
            "- A time and place free of stress, ideally with a private bathroom\n"
            "- Painkillers such as ibuprofen 400-600 mg ready in advance\n"
            "- Think in advance about where to go if extra care is needed.\n\n"
            "Do you have any questions so far?"
        ),
        buttons=[{"id": "plan_ready", "title": "Ready for steps"}, {"id": "plan_ask", "title": "I have a question"}]
    )


def on_plan(s, oid, value):
    if oid == "plan_ask":
        # The AI answers typed questions; this button means she wants to write one.
        send_text(s["phone"], f"Please type your question, {name_of(s)}.")
        s["step"] = "PLAN_QUESTION"
    else:
        go(s, "METHOD")


def ask_plan_question(s):
    send_text(s["phone"], "Please type your question, or type *ready* to continue to the steps.")


def on_plan_question(s, oid, value):
    # Questions are answered by the AI first. If the AI is off, a counselor takes the question.
    if looks_like_question(value):
        send_text(s["phone"], "Thank you. A counselor will answer your question here directly.")
        s["data"]["questions_asked"] = value[:200]
        hand_to_human(s)
    else:
        go(s, "METHOD")


def ask_method(s):
    # 4.1 & Method selection
    send_buttons(
        s["phone"],
        body_text=(
            "The next messages explain how the pills are used. It helps to have a pen and paper to write the steps down.\n\n"
            "Which pills will you be using?"
        ),
        buttons=[{"id": "m_miso_only", "title": "Misoprostol alone"}, {"id": "m_combo", "title": "Mife + Misoprostol"}]
    )


def on_method(s, oid, value):
    if oid == "m_combo":
        s["data"]["pill_choice"] = "Mifepristone + Misoprostol"
        steps_text = (
            "*How to take Mifepristone with Misoprostol (1 + 4 pills):*\n\n"
            "Step 1: Swallow 1 mifepristone tablet (200 mg) with a glass of water.\n\n"
            "Step 2: 24 hours later, put 4 misoprostol pills (200 mcg each) between the gum and cheek (2 on left, 2 on right). "
            "Leave them there for 30 minutes to dissolve. After 30 minutes, swallow whatever remains."
        )
    else:
        s["data"]["pill_choice"] = "Misoprostol alone"
        steps_text = (
            "*How to take Misoprostol alone (12 pills total):*\n"
            "The most effective way is to put 4 pills under the tongue every 3 hours, 3 times.\n\n"
            "Step 1: Put 4 pills under the tongue. Do not swallow for 30 minutes while they dissolve. After 30 mins, swallow what is left.\n"
            "Step 2: 3 hours later, put another 4 pills under the tongue for 30 minutes.\n"
            "Step 3: 3 hours later, put the last 4 pills under the tongue for 30 minutes."
        )
    send_text(s["phone"], steps_text)
    # 4.3 Eating/drinking & 4.5 - 4.7 Symptoms
    send_text(s["phone"], (
        "📌 *Important rules & what to expect:*\n"
        "- Do not eat or drink during the 30 minutes while pills are dissolving. Normal eating/drinking before and after is fine.\n"
        "- Normal side effects: cramps, chills, mild fever, nausea, diarrhea.\n"
        "- Bleeding usually starts 2 to 4 hours after misoprostol. Heaviest bleeding lasts 1 to 4 hours with clots, then eases.\n"
        "- Pain relief: Ibuprofen 600 mg can be taken after the first misoprostol dose."
    ))
    go(s, "UNDERSTANDING")


def ask_understanding(s):
    send_text(s["phone"], "Can you tell us, in your own words, how the pills are taken? Do you have any doubts?")


def on_understanding(s, oid, value):
    s["data"]["understanding"] = value
    send_warning_signs(s["phone"])
    go(s, "WARN_CHECK")


# ----- STAGE 5: SIGNS OF COMPLICATION ----------------------------------------
def ask_warn_check(s):
    # 5.4 Check understanding
    send_buttons(
        s["phone"],
        body_text="Are the 4 warning signs clear to you?",
        buttons=[{"id": "warn_clear", "title": "Yes, all clear"}, {"id": "warn_repeat", "title": "Please repeat"}]
    )


def on_warn_check(s, oid, value):
    if oid == "warn_repeat":
        send_warning_signs(s["phone"])
        ask(s)
    else:
        go(s, "CONTRACEPTION")


# ----- STAGE 6: AFTER THE ABORTION & CONTRACEPTION ---------------------------
def ask_contraception(s):
    send_buttons(
        s["phone"],
        body_text=(
            "📌 *After the abortion:*\n"
            "- Bleeding decreases gradually and can continue 1 to 3 weeks.\n"
            "- Normal period usually returns in 4 to 6 weeks.\n"
            "- Precaution: Do not put anything in the vagina (no sex, tampons, baths) for the first 2 to 3 days.\n"
            "- Confirming success: Take a pregnancy test in 3 to 4 weeks (a test done earlier can show a false positive).\n\n"
            "You can get pregnant again immediately after an abortion.\n"
            "Would you like information about contraception?"
        ),
        buttons=[{"id": "contra_yes", "title": "Yes"}, {"id": "contra_no", "title": "No, thank you"}]
    )


def on_contraception(s, oid, value):
    s["data"]["contraception_info"] = value
    if oid == "contra_yes":
        send_stage_6_3_contraception(s["phone"])
    go(s, "FOLLOWUP")


# ----- STAGE 7: CLOSING AND FOLLOW-UP ----------------------------------------
def ask_followup(s):
    send_text(s["phone"], (
        f"Do you have any other question or concern, {name_of(s)}?\n\n"
        "Would you like us to check in with you later? If yes, please tell us which day and time is safe to message."
    ))


def on_followup(s, oid, value):
    s["data"]["followup_time"] = value
    send_text(s["phone"], (
        f"Thank you, {name_of(s)}. We have noted that. "
        "You can always write to Aunty Queen again whenever you have questions or worries. "
        "We wish you the very best. Take good care.\n\n"
        "— *A counselor is available here if you need any further human support.*"
    ))
    hand_to_human(s, status="completed")


# ----- Option 2: already used the pills --------------------------------------
def ask_triage(s):
    send_buttons(
        s["phone"],
        body_text=(
            f"{name_of(s)}, are you experiencing any of these 4 warning signs right now?\n"
            "1. Soaking 2+ pads/hour for 2 hours\n"
            "2. Severe pain unrelieved by painkillers\n"
            "3. Bad-smelling vaginal discharge\n"
            "4. Fever over 38°C"
        ),
        buttons=[{"id": "warn_report_yes", "title": "Yes, I have them"}, {"id": "warn_report_no", "title": "No, I do not"}]
    )


def on_triage(s, oid, value):
    if oid == "warn_report_yes":
        s["data"]["warning_signs"] = "YES"
        send_text(s["phone"], URGENT_TEXT)
        hand_to_human(s, status="URGENT")
    else:
        s["data"]["warning_signs"] = "No"
        send_text(s["phone"], f"Thank you for confirming, {name_of(s)}. A counselor will review your symptoms with you directly.")
        hand_to_human(s)


# ----- Reusable blocks -------------------------------------------------------
def send_warning_signs(sender_id):
    # 5.1, 5.2, 5.3 The four warning signs
    send_text(sender_id, (
        "Thank you. Now, here are the *4 Warning Signs of Complication* to always remember:\n\n"
        "1. *Too much bleeding*: soaking more than 2 maxi pads per hour for 2 or 3 consecutive hours, or bleeding like an open tap.\n"
        "2. *Severe pain* that painkillers do not relieve.\n"
        "3. *Bad-smelling* vaginal discharge.\n"
        "4. *Fever* over 38°C for more than 24 hours, or over 39°C at any time.\n\n"
        "🏥 *Getting care*: Any complication is treated exactly like a miscarriage. A woman can always go to any clinic and say she had a miscarriage."
    ))


def send_stage_6_3_contraception(sender_id):
    send_text(sender_id, (
        "*Contraception Methods (6.3a):*\n\n"
        "- *Pill, patch, injection, implant*: Can be started up to 5 days after taking misoprostol and protect immediately.\n"
        "- *Vaginal ring*: Can be inserted as soon as 2 or 3 days after misoprostol.\n"
        "- *IUD*: Inserted once complete abortion is confirmed, or during the next period.\n"
        "- *Condoms, barrier methods*: Can be used as soon as sex is resumed.\n"
        "- *Fertility awareness*: Once regular cycles return."
    ))


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
