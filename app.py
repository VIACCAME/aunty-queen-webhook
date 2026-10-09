import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "aunty_queen_secret_123")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
FLOW_ID = os.environ.get("FLOW_ID", "2033800373990985")

# In-memory session store (tracks user state and responses)
# In production, back this with Redis, PostgreSQL, or Supabase
sessions = {}

GRAPH_URL = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json"
}

@app.route("/", methods=["GET"])
def home():
    return "Aunty Queen Hotline Webhook is live!", 200

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
    data = request.get_json()

    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return jsonify({"status": "no_messages"}), 200

        msg = messages[0]
        sender_id = msg.get("from")
        msg_type = msg.get("type")

        # Initialize session state if new user
        if sender_id not in sessions:
            sessions[sender_id] = {
                "step": "START",
                "lang": "en",
                "name": "",
                "intent": ""
            }

        session = sessions[sender_id]

        # -------------------------------------------------------------
        # 1. HANDLE FLOW SUBMISSIONS (User submitted the Meta Flow)
        # -------------------------------------------------------------
        if msg_type == "interactive" and "nfm_reply" in msg.get("interactive", {}):
            flow_data = msg["interactive"]["nfm_reply"].get("response_json")
            print(f"[FLOW COMPLETED] from {sender_id}: {flow_data}")
            
            client_name = session.get("name", "there")
            send_text(
                sender_id,
                f"Thank you, {client_name}. Aunty Queen has safely received your details. "
                "A confidential counselor will review your information and be with you shortly. "
                "\n\n*Reminder:* You can turn on disappearing messages or delete this chat whenever you wish to keep your phone private."
            )
            session["step"] = "HANDOFF_TO_HUMAN"
            return jsonify({"status": "flow_handled"}), 200

        # Extract text or button / list responses
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

        # -------------------------------------------------------------
        # STEP 0: START -> LANGUAGE SELECTION
        # -------------------------------------------------------------
        if current_step == "START":
            send_buttons(
                sender_id,
                body_text="Welcome to Aunty Queen Hotline.\nPlease select your preferred language / Choisissez votre langue :",
                buttons=[
                    {"id": "lang_en", "title": "English"},
                    {"id": "lang_fr", "title": "Français"}
                ],
                footer_text="Aunty Queen Confidential Service"
            )
            session["step"] = "AWAITING_LANG"

        # -------------------------------------------------------------
        # STEP 1: AWAITING LANGUAGE -> WELCOME & CONSENT (1.1, 1.2, 1.3)
        # -------------------------------------------------------------
        elif current_step == "AWAITING_LANG":
            if button_id == "lang_fr" or user_input.lower() in ["2", "french", "français"]:
                session["lang"] = "fr"
            else:
                session["lang"] = "en"

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

        # -------------------------------------------------------------
        # STEP 2: CONSENT CHECK (1.3 / 1.3a)
        # -------------------------------------------------------------
        elif current_step == "AWAITING_CONSENT":
            if button_id == "consent_explain" or "what" in user_input.lower():
                explanation = (
                    "We ask about: age, date of last period, whether pregnancy is confirmed, "
                    "reason for reaching out, and whether someone is supporting you.\n\n"
                    "Any question can be skipped.\n\n"
                    "What name would you like us to call you?"
                )
                send_text(sender_id, explanation)
                session["step"] = "AWAITING_NAME"
            else:
                send_text(sender_id, "Thank you. What name or nickname would you like us to call you?")
                session["step"] = "AWAITING_NAME"

        # -------------------------------------------------------------
        # STEP 3: CAPTURE NAME -> PRESENT SERVICE MENU (1.4)
        # -------------------------------------------------------------
        elif current_step == "AWAITING_NAME":
            client_name = user_input if user_input else "Friend"
            session["name"] = client_name

            menu_body = (
                f"Thank you, {client_name}.\n\n"
                "How can we support you today? Please choose an option below:"
            )
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
                                "title": "1. Safe abortion pills",
                                "description": "Information on safe abortion with pills up to 12 weeks"
                            },
                            {
                                "id": "opt_already_used",
                                "title": "2. Already used pills",
                                "description": "I have taken pills and have questions or symptoms"
                            },
                            {
                                "id": "opt_contraception",
                                "title": "3. Contraception",
                                "description": "Information on family planning and birth control"
                            },
                            {
                                "id": "opt_other",
                                "title": "4. Something else",
                                "description": "Speak with a counselor about another topic"
                            }
                        ]
                    }
                ]
            )
            session["step"] = "AWAITING_SERVICE_CHOICE"

        # -------------------------------------------------------------
        # STEP 4: ROUTE BASED ON CHOICE (1.4 & 1.5)
        # -------------------------------------------------------------
        elif current_step == "AWAITING_SERVICE_CHOICE":
            client_name = session.get("name", "there")

            # Route 1: Safe Abortion Pills -> Launch Flow
            if button_id == "opt_pills_info" or user_input.startswith("1"):
                session["intent"] = "pills_info"
                send_interactive_flow(
                    sender_id,
                    header_text="Intake Support",
                    body_text=(
                        f"{client_name}, Aunty Queen shares scientific information about safe self-managed "
                        "abortion with pills for pregnancies up to 12 weeks, as well as clinic procedures (MVA).\n\n"
                        "Please tap below to answer a few brief questions so our team can provide tailored guidance."
                    ),
                    button_label="Open Intake Form"
                )
                session["step"] = "IN_FLOW"

            # Route 2: Already Used Pills -> Warning Signs Check (Stage 5)
            elif button_id == "opt_already_used" or user_input.startswith("2"):
                session["intent"] = "used_pills"
                warning_signs_msg = (
                    f"{client_name}, we are here to support you.\n\n"
                    "⚠️ *Please check if you are experiencing any of these 4 warning signs:*\n"
                    "1. Too much bleeding (soaking 2+ maxi pads/hour for 2+ hours)\n"
                    "2. Severe pain that painkillers do not relieve\n"
                    "3. Vaginal discharge that smells bad\n"
                    "4. Fever over 38°C for more than 24 hours, or over 39°C at any time\n\n"
                    "Are you experiencing any of these right now?"
                )
                send_buttons(
                    sender_id,
                    body_text=warning_signs_msg,
                    buttons=[
                        {"id": "warning_yes", "title": "Yes, I have them"},
                        {"id": "warning_no", "title": "No, I am okay"}
                    ]
                )
                session["step"] = "STAGE_5_TRIAGE"

            # Route 3: Contraception (6.3)
            elif button_id == "opt_contraception" or user_input.startswith("3"):
                session["intent"] = "contraception"
                send_text(
                    sender_id,
                    f"{client_name}, you can get pregnant again immediately after an abortion or period. "
                    "Hormonal methods (pills, implants, injections) can be started right away.\n\n"
                    "A counselor is being connected to discuss which method best suits your lifestyle."
                )
                session["step"] = "HANDOFF_TO_HUMAN"

            # Route 4: Something else
            else:
                session["intent"] = "other"
                send_text(
                    sender_id,
                    f"Please tell us in your own words what you need assistance with, {client_name}. "
                    "A counselor will read your message and reply."
                )
                session["step"] = "HANDOFF_TO_HUMAN"

        # -------------------------------------------------------------
        # STEP 5: WARNING SIGNS TRIAGE (Quick Reply handling)
        # -------------------------------------------------------------
        elif current_step == "STAGE_5_TRIAGE":
            if button_id == "warning_yes" or "yes" in user_input.lower():
                send_text(
                    sender_id,
                    "🚨 *Urgent Medical Advice:*\n"
                    "What you describe is a sign that requires immediate medical care. "
                    "Please go to the nearest hospital or health clinic now.\n\n"
                    "Any complication is treated exactly the same as for a miscarriage, and you can simply say you had a miscarriage. "
                    "Message us when you are safe; we are here."
                )
            else:
                send_text(
                    sender_id,
                    "Thank you for confirming. A counselor is reviewing your chat history and will respond shortly to address your questions."
                )
            session["step"] = "HANDOFF_TO_HUMAN"

        # -------------------------------------------------------------
        # STEP 6: HUMAN HANDOFF ACTIVE
        # -------------------------------------------------------------
        elif current_step == "HANDOFF_TO_HUMAN":
            # Bot remains silent so counselors can chat without automation interference
            pass

    except Exception as e:
        print(f"Error handling message: {e}")

    return jsonify({"status": "success"}), 200


# ---------------------------------------------------------------------
# HELPER FUNCTIONS (WhatsApp Cloud API)
# ---------------------------------------------------------------------

def send_text(recipient_id, text_body):
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_id,
        "type": "text",
        "text": {"body": text_body}
    }
    requests.post(GRAPH_URL, headers=HEADERS, json=payload)

def send_buttons(recipient_id, body_text, buttons, header_text=None, footer_text=None):
    """Sends 1 to 3 interactive reply buttons (Meta limit: max 3)."""
    interactive_obj = {
        "type": "button",
        "body": {"text": body_text},
        "action": {
            "buttons": [
                {
                    "type": "reply",
                    "reply": {"id": b["id"], "title": b["title"][:20]}
                }
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
    requests.post(GRAPH_URL, headers=HEADERS, json=payload)

def send_list_menu(recipient_id, body_text, button_label, sections, header_text=None, footer_text=None):
    """Sends an interactive menu (up to 10 options)."""
    interactive_obj = {
        "type": "list",
        "body": {"text": body_text},
        "action": {
            "button": button_label[:20],
            "sections": sections
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
    requests.post(GRAPH_URL, headers=HEADERS, json=payload)

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
                    "flow_action_payload": {
                        "screen": "BASIC_INFO"
                    }
                }
            }
        }
    }
    requests.post(GRAPH_URL, headers=HEADERS, json=payload)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
