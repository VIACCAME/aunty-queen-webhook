import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "aunty_queen_secret_123")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
FLOW_ID = os.environ.get("FLOW_ID", "")
GOOGLE_SHEET_WEBHOOK_URL = os.environ.get("GOOGLE_SHEET_WEBHOOK_URL")

# In-memory session tracking
sessions = {}

def get_graph_url():
    return f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"

def get_headers():
    return {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

@app.route("/", methods=["GET"])
def home():
    return "Aunty Queen Hotline Webhook is running!", 200

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403

@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json(silent=True) or {}

    try:
        entry = data.get("entry", [])
        if not entry:
            return jsonify({"status": "ignored"}), 200

        changes = entry[0].get("changes", [])
        if not changes:
            return jsonify({"status": "ignored"}), 200

        value = changes[0].get("value", {})
        messages = value.get("messages", [])

        # Ignore delivery receipts, read statuses, etc.
        if not messages:
            return jsonify({"status": "no_messages"}), 200

        msg = messages[0]
        sender_id = msg.get("from")
        msg_type = msg.get("type")

        if not sender_id:
            return jsonify({"status": "no_sender"}), 200

        # Initialize session state if new user
        if sender_id not in sessions:
            sessions[sender_id] = {
                "step": "START",
                "lang": "en",
                "name": "Friend",
                "intent": ""
            }

        session = sessions[sender_id]

        # 1. Handle Flow form completion
        if msg_type == "interactive" and "nfm_reply" in msg.get("interactive", {}):
            flow_data = msg["interactive"]["nfm_reply"].get("response_json", {})
            print(f"[FLOW COMPLETED] from {sender_id}: {flow_data}")

            # Send intake data to Google Sheets
            save_to_google_sheets({
                "phone": sender_id,
                "name": session.get("name", ""),
                "language": session.get("lang", "en"),
                "category": "Intake Flow",
                "age": flow_data.get("age", ""),
                "location": flow_data.get("location", ""),
                "currently_pregnant": flow_data.get("currently_pregnant", ""),
                "gestational_age": flow_data.get("gestational_age", ""),
                "notes": flow_data.get("reason", "")
            })

            send_text(
                sender_id,
                f"Thank you, {session.get('name')}. Aunty Queen has safely received your details. "
                "A confidential counselor will review your information and be with you shortly.\n\n"
                "*Tip:* You can turn on disappearing messages or delete this chat to keep your phone private."
            )
            session["step"] = "HANDOFF_TO_HUMAN"
            return jsonify({"status": "flow_handled"}), 200

        # Extract text or button / list choice
        user_input = ""
        button_id = ""

        if msg_type == "text":
            user_input = msg.get("text", {}).get("body", "").strip()
        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            if interactive.get("type") == "button_reply":
                button_id = interactive["button_reply"]["id"]
                user_input = interactive["button_reply"]["title"]
            elif interactive.get("type") == "list_reply":
                button_id = interactive["list_reply"]["id"]
                user_input = interactive["list_reply"]["title"]

        current_step = session["step"]

        # STEP 0: LANGUAGE SELECTION
        if current_step == "START":
            send_buttons(
                sender_id,
                body_text="Welcome to Aunty Queen Hotline.\nPlease select your preferred language / Choisissez votre langue :",
                buttons=[
                    {"id": "lang_en", "title": "English"},
                    {"id": "lang_fr", "title": "Français"}
                ],
                footer_text="Confidential Service"
            )
            session["step"] = "AWAITING_LANG"

        # STEP 1: WELCOME & CONSENT
        elif current_step == "AWAITING_LANG":
            session["lang"] = "fr" if (button_id == "lang_fr" or "fr" in user_input.lower()) else "en"

            welcome_msg = (
                "Hello, and welcome to Aunty Queen Hotline.\n\n"
                "We share general information on sexual and reproductive health, "
                "including safe abortion information based on World Health Organization guidelines.\n\n"
                "🔒 *Confidentiality & Chat Safety:*\n"
                "Everything shared in this chat is kept strictly confidential and used only for our records. "
                "To keep this chat private on your phone, you can turn on disappearing messages or delete the chat when we finish.\n\n"
                "To support you well, we will need to ask a few personal questions. Would that be OK?"
            )
            send_buttons(
                sender_id,
                body_text=welcome_msg,
                buttons=[
                    {"id": "consent_yes", "title": "Yes, that is OK"},
                    {"id": "consent_explain", "title": "What will you ask?"}
                ]
            )
            session["step"] = "AWAITING_CONSENT"

        # STEP 2: CONSENT RESPONSE
        elif current_step == "AWAITING_CONSENT":
            if button_id == "consent_explain" or "what" in user_input.lower():
                explanation = (
                    "We ask about: age, date of last period, whether pregnancy is confirmed, "
                    "reason for reaching out, and whether someone is supporting you.\n\n"
                    "Any question can be skipped.\n\n"
                    "What name or nickname would you like us to call you?"
                )
                send_text(sender_id, explanation)
            else:
                send_text(sender_id, "Thank you. What name or nickname would you like us to call you?")
            session["step"] = "AWAITING_NAME"

        # STEP 3: NAME CAPTURE -> MENU
        elif current_step == "AWAITING_NAME":
            client_name = user_input if user_input else "Friend"
            session["name"] = client_name

            menu_body = f"Thank you, {client_name}.\n\nHow can we support you today?"
            send_list_menu(
                sender_id,
                body_text=menu_body,
                button_label="Choose Option",
                sections=[
                    {
                        "title": "Aunty Queen Support",
                        "rows": [
                            {
                                "id": "opt_pills_info",
                                "title": "Safe abortion pills",
                                "description": "Information on pills up to 12 weeks"
                            },
                            {
                                "id": "opt_already_used",
                                "title": "Already used pills",
                                "description": "Questions, bleeding, or symptoms"
                            },
                            {
                                "id": "opt_contraception",
                                "title": "Contraception",
                                "description": "Family planning and birth control"
                            },
                            {
                                "id": "opt_other",
                                "title": "Something else",
                                "description": "Speak with a counselor"
                            }
                        ]
                    }
                ]
            )
            session["step"] = "AWAITING_SERVICE_CHOICE"

        # STEP 4: SERVICE ROUTING
        elif current_step == "AWAITING_SERVICE_CHOICE":
            client_name = session.get("name", "there")

            if button_id == "opt_pills_info" or "1" in user_input or "pill" in user_input.lower():
                session["intent"] = "pills_info"
                if FLOW_ID:
                    send_interactive_flow(
                        sender_id,
                        header_text="Intake Support",
                        body_text=f"{client_name}, tap below to complete our confidential intake form so our team can provide tailored guidance.",
                        button_label="Open Intake Form"
                    )
                    session["step"] = "IN_FLOW"
                else:
                    send_text(sender_id, f"{client_name}, a counselor will guide you through our safe abortion information shortly.")
                    session["step"] = "HANDOFF_TO_HUMAN"

            elif button_id == "opt_already_used" or "2" in user_input:
                session["intent"] = "used_pills"
                warning_msg = (
                    f"{client_name}, we are here to support you.\n\n"
                    "⚠️ *Are you experiencing any of these 4 warning signs right now?*\n"
                    "1. Soaking 2+ maxi pads/hour for 2+ hours\n"
                    "2. Severe pain that painkillers do not relieve\n"
                    "3. Vaginal discharge that smells bad\n"
                    "4. Fever over 38°C for 24+ hours or over 39°C at any time"
                )
                send_buttons(
                    sender_id,
                    body_text=warning_msg,
                    buttons=[
                        {"id": "warning_yes", "title": "Yes, I have them"},
                        {"id": "warning_no", "title": "No, I am okay"}
                    ]
                )
                session["step"] = "STAGE_5_TRIAGE"

            elif button_id == "opt_contraception" or "3" in user_input:
                session["intent"] = "contraception"
                send_text(
                    sender_id,
                    f"{client_name}, a woman can get pregnant again immediately after an abortion or period. "
                    "Hormonal methods can be started right away. A counselor will be right with you to discuss options."
                )
                session["step"] = "HANDOFF_TO_HUMAN"

            else:
                session["intent"] = "other"
                send_text(sender_id, f"Please tell us in your own words what you need assistance with, {client_name}. A counselor will reply shortly.")
                session["step"] = "HANDOFF_TO_HUMAN"

        # STEP 5: WARNING SIGNS TRIAGE
        elif current_step == "STAGE_5_TRIAGE":
            if button_id == "warning_yes" or "yes" in user_input.lower():
                send_text(
                    sender_id,
                    "🚨 *Urgent Medical Advice:*\n"
                    "What you describe is a sign that requires immediate medical care. "
                    "Please go to the nearest hospital or health clinic now.\n\n"
                    "The treatment is the same as for a miscarriage, and you can say you had a miscarriage. "
                    "Message us when you can; we are here."
                )
            else:
                send_text(sender_id, "Thank you for letting us know. A counselor is reviewing your chat and will assist you shortly.")
            session["step"] = "HANDOFF_TO_HUMAN"

        elif current_step == "HANDOFF_TO_HUMAN":
            # Handed off: silently let human counselors talk
            pass

    except Exception as e:
        print(f"[ERROR in receive_message]: {e}")

    return jsonify({"status": "success"}), 200

# API Helpers
def send_text(recipient_id, text_body):
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_id,
        "type": "text",
        "text": {"body": text_body}
    }
    r = requests.post(get_graph_url(), headers=get_headers(), json=payload)
    print(f"send_text response: {r.status_code}")

def send_buttons(recipient_id, body_text, buttons, header_text=None, footer_text=None):
    interactive_obj = {
        "type": "button",
        "body": {"text": body_text},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
                for b in buttons
            ]
        }
    }
    if header_text:
        interactive_obj["header"] = {"type": "text", "text": header_text}
    if footer_text:
        interactive_obj["footer"] = {"text": footer_text}

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_id,
        "type": "interactive",
        "interactive": interactive_obj
    }
    r = requests.post(get_graph_url(), headers=get_headers(), json=payload)
    print(f"send_buttons response: {r.status_code}")

def send_list_menu(recipient_id, body_text, button_label, sections):
    interactive_obj = {
        "type": "list",
        "body": {"text": body_text},
        "action": {
            "button": button_label[:20],
            "sections": sections
        }
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_id,
        "type": "interactive",
        "interactive": interactive_obj
    }
    r = requests.post(get_graph_url(), headers=get_headers(), json=payload)
    print(f"send_list_menu response: {r.status_code}")

def send_interactive_flow(recipient_id, header_text, body_text, button_label):
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_id,
        "type": "interactive",
        "interactive": {
            "type": "flow",
            "header": {"type": "text", "text": header_text},
            "body": {"text": body_text},
            "footer": {"text": "Aunty Queen Confidential"},
            "action": {
                "name": "flow",
                "parameters": {
                    "flow_message_version": "3",
                    "flow_token": f"token_{recipient_id}",
                    "flow_id": FLOW_ID,
                    "flow_cta": button_label,
                    "flow_action": "navigate",
                    "flow_action_payload": {"screen": "BASIC_INFO"}
                }
            }
        }
    }
    r = requests.post(get_graph_url(), headers=get_headers(), json=payload)
    print(f"send_interactive_flow response: {r.status_code}")

def save_to_google_sheets(payload):
    if not GOOGLE_SHEET_WEBHOOK_URL:
        return
    try:
        requests.post(
            GOOGLE_SHEET_WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            allow_redirects=True,
            timeout=10
        )
    except Exception as e:
        print(f"Google Sheet logging error: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
