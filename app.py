import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "aunty_queen_secret_123")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
FLOW_ID = os.environ.get("FLOW_ID", "")
GOOGLE_SHEET_WEBHOOK_URL = os.environ.get("GOOGLE_SHEET_WEBHOOK_URL")

sessions = {}

def send_meta_request(payload):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    r = requests.post(url, headers=headers, json=payload)
    print(f"[API Response {r.status_code}]: {r.text}")
    return r

@app.route("/", methods=["GET"])
def home():
    return "Aunty Queen Hotline Webhook Active", 200

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

        if not messages:
            return jsonify({"status": "no_messages"}), 200

        msg = messages[0]
        sender_id = msg.get("from")
        msg_type = msg.get("type")

        if not sender_id:
            return jsonify({"status": "no_sender"}), 200

        if sender_id not in sessions:
            sessions[sender_id] = {
                "step": "START",
                "lang": "en",
                "name": "Friend",
                "category": ""
            }

        session = sessions[sender_id]

        # 1. User submitted the Meta Flow
        if msg_type == "interactive" and "nfm_reply" in msg.get("interactive", {}):
            flow_data = msg["interactive"]["nfm_reply"].get("response_json", {})
            print(f"[FLOW COMPLETED] {sender_id}: {flow_data}")

            save_to_google_sheets({
                "phone": sender_id,
                "name": session.get("name", ""),
                "language": session.get("lang", "en"),
                "category": session.get("category", "Intake Flow"),
                "age": flow_data.get("age", ""),
                "location": flow_data.get("location", ""),
                "currently_pregnant": flow_data.get("currently_pregnant", ""),
                "gestational_age": flow_data.get("gestational_age", ""),
                "notes": f"LMP: {flow_data.get('last_menstrual_period', '')} | Reason: {flow_data.get('reason', '')}"
            })

            confirmation = (
                f"Thank you, {session.get('name')}. Aunty Queen has received your details.\n\n"
                "A counselor is reviewing your information and will be with you shortly. "
                "Remember you can delete this chat or turn on disappearing messages anytime for privacy."
            )
            send_text(sender_id, confirmation)
            session["step"] = "HANDOFF_TO_HUMAN"
            return jsonify({"status": "flow_handled"}), 200

        # Read text or button reply
        user_input = ""
        button_id = ""

        if msg_type == "text":
            user_input = msg.get("text", {}).get("body", "").strip()
        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            if interactive.get("type") == "button_reply":
                button_id = interactive["button_reply"]["id"]
                user_input = interactive["button_reply"]["title"]

        current_step = session["step"]

        # STEP 0: START -> Language selection buttons
        if current_step == "START":
            send_buttons(
                sender_id,
                body_text="Hello, and welcome to Aunty Queen Hotline.\n\nPlease choose your language / Choisissez votre langue :",
                buttons=[
                    {"id": "lang_en", "title": "English"},
                    {"id": "lang_fr", "title": "Français"}
                ],
                footer_text="Aunty Queen Hotline"
            )
            session["step"] = "AWAITING_LANG"

        # STEP 1: Consent & Privacy check
        elif current_step == "AWAITING_LANG":
            session["lang"] = "fr" if (button_id == "lang_fr" or "fr" in user_input.lower()) else "en"

            if session["lang"] == "fr":
                body = (
                    "Tout ce qui est partagé dans cette discussion reste strictement confidentiel.\n\n"
                    "Pour bien vous soutenir, nous aimerions vous poser quelques questions. Êtes-vous d'accord ?"
                )
                btn_yes = "Oui, c'est bon"
                btn_info = "Que demandez-vous ?"
            else:
                body = (
                    "Everything shared in this chat is kept strictly confidential.\n\n"
                    "To support you well, we will need to ask a few personal questions. Would that be OK?"
                )
                btn_yes = "Yes, that is OK"
                btn_info = "What we ask?"

            send_buttons(
                sender_id,
                body_text=body,
                buttons=[
                    {"id": "consent_yes", "title": btn_yes},
                    {"id": "consent_explain", "title": btn_info}
                ]
            )
            session["step"] = "AWAITING_CONSENT"

        # STEP 2: Name capture
        elif current_step == "AWAITING_CONSENT":
            if session["lang"] == "fr":
                if button_id == "consent_explain":
                    send_text(sender_id, "Nous demandons votre âge, date des dernières règles et votre situation. Tout peut être ignoré.\n\nQuel nom souhaitez-vous qu'on utilise ?")
                else:
                    send_text(sender_id, "Merci. Quel prénom ou pseudonyme souhaitez-vous qu'on utilise ?")
            else:
                if button_id == "consent_explain":
                    send_text(sender_id, "We ask about age, last period, and your situation. Any question can be skipped.\n\nWhat name would you like us to call you?")
                else:
                    send_text(sender_id, "Thank you. What name or nickname would you like us to call you?")
            session["step"] = "AWAITING_NAME"

        # STEP 3: Main Topic Selection
        elif current_step == "AWAITING_NAME":
            client_name = user_input if user_input else "Friend"
            session["name"] = client_name

            if session["lang"] == "fr":
                menu = (
                    f"Merci, {client_name}.\n\nComment pouvons-nous vous aider aujourd'hui ? Répondez par le chiffre :\n"
                    "1. Information sur les pilules abortives\n"
                    "2. J'ai déjà pris les pilules (questions/signes)\n"
                    "3. Contraception\n"
                    "4. Autre chose"
                )
            else:
                menu = (
                    f"Thank you, {client_name}.\n\nHow can we support you today? Reply with a number:\n"
                    "1. Abortion with pills info\n"
                    "2. Already used pills (questions/signs)\n"
                    "3. Contraception\n"
                    "4. Something else"
                )
            send_text(sender_id, menu)
            session["step"] = "AWAITING_CHOICE"

        # STEP 4: Branching -> Flow or Direct Triage
        elif current_step == "AWAITING_CHOICE":
            client_name = session.get("name", "there")

            if "1" in user_input or "pill" in user_input.lower():
                session["category"] = "Abortion with pills"
                # Launch the Meta Flow
                flow_launched = send_interactive_flow(
                    sender_id,
                    header_text="Intake Support",
                    body_text=f"{client_name}, please tap below to complete our short confidential form.",
                    button_label="Open Intake Form"
                )
                # Fallback if Flow ID is missing/invalid
                if not flow_launched:
                    send_text(sender_id, f"{client_name}, a counselor has been notified and will guide you step by step in just a moment.")
                    session["step"] = "HANDOFF_TO_HUMAN"
                else:
                    session["step"] = "IN_FLOW"

            elif "2" in user_input:
                session["category"] = "Already used pills"
                warning_msg = (
                    f"{client_name}, are you experiencing any of these 4 warning signs right now?\n"
                    "- Soaking 2+ pads/hour for 2 hours\n"
                    "- Severe unrelieved pain\n"
                    "- Bad-smelling discharge\n"
                    "- Fever over 38°C"
                )
                send_buttons(
                    sender_id,
                    body_text=warning_msg,
                    buttons=[
                        {"id": "warn_yes", "title": "Yes, I have signs"},
                        {"id": "warn_no", "title": "No, I am okay"}
                    ]
                )
                session["step"] = "STAGE_5_TRIAGE"

            elif "3" in user_input:
                session["category"] = "Contraception"
                send_text(sender_id, f"{client_name}, a counselor will connect with you here shortly to discuss contraceptive options.")
                save_to_google_sheets({
                    "phone": sender_id, "name": client_name, "language": session.get("lang"),
                    "category": "Contraception", "notes": "Requested family planning info"
                })
                session["step"] = "HANDOFF_TO_HUMAN"

            else:
                session["category"] = "Other"
                send_text(sender_id, f"Please tell us in your own words what you need assistance with, {client_name}. A counselor will reply directly.")
                session["step"] = "HANDOFF_TO_HUMAN"

        # STEP 5: Complication triage check
        elif current_step == "STAGE_5_TRIAGE":
            if button_id == "warn_yes" or "yes" in user_input.lower():
                send_text(
                    sender_id,
                    "🚨 *Urgent Medical Advice:*\n"
                    "What you describe is a sign that requires immediate medical care. "
                    "Please go to the nearest hospital or health clinic now.\n\n"
                    "The treatment is the same as for a miscarriage, and you can say you had a miscarriage. "
                    "Message us when you are safe; we are here."
                )
            else:
                send_text(sender_id, "Thank you for confirming. A counselor is reading your chat and will be right with you.")
            
            save_to_google_sheets({
                "phone": sender_id, "name": session.get("name"), "language": session.get("lang"),
                "category": "Already used pills", "notes": f"Warning signs: {user_input}"
            })
            session["step"] = "HANDOFF_TO_HUMAN"

        elif current_step == "HANDOFF_TO_HUMAN":
            # Handover complete: silent so humans can chat freely
            pass

    except Exception as e:
        print(f"[ERROR in receive_message]: {e}")

    return jsonify({"status": "success"}), 200

# Helpers
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
    interactive_obj = {
        "type": "button",
        "body": {"text": body_text[:1024]},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
                for b in buttons
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

def send_interactive_flow(recipient_id, header_text, body_text, button_label):
    if not FLOW_ID:
        return False
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_id,
        "type": "interactive",
        "interactive": {
            "type": "flow",
            "header": {"type": "text", "text": header_text},
            "body": {"text": body_text},
            "footer": {"text": "Aunty Queen Hotline"},
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
    r = send_meta_request(payload)
    return r.status_code == 200

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
        print(f"Sheet error: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
