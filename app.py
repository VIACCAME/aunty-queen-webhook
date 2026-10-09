import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "aunty_queen_secret_123")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
FLOW_ID = os.environ.get("FLOW_ID", "2033800373990985")

@app.route("/", methods=["GET"])
def home():
    return "Webhook is active and running!", 200

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

        if messages:
            msg = messages[0]
            sender_id = msg.get("from")
            msg_type = msg.get("type")

            # 1. Flow submission received
            if msg_type == "interactive" and "nfm_reply" in msg.get("interactive", {}):
                flow_data = msg["interactive"]["nfm_reply"].get("response_json")
                print(f"Flow submission received from {sender_id}: {flow_data}")
                send_simple_text(
                    sender_id,
                    "Thank you! Our support team has received your details and will get in touch shortly."
                )
                return jsonify({"status": "received"}), 200

            # 2. Trigger flow on incoming user message
            elif sender_id:
                send_interactive_flow(sender_id)

    except Exception as e:
        print(f"Error handling webhook: {e}")

    return jsonify({"status": "success"}), 200

def send_interactive_flow(recipient_id):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_id,
        "type": "interactive",
        "interactive": {
            "type": "flow",
            "header": {
                "type": "text",
                "text": "Welcome to Aunty Queen"
            },
            "body": {
                "text": "Hi! Please tap below to fill out our confidential intake form."
            },
            "footer": {
                "text": "Secure intake support"
            },
            "action": {
                "name": "flow",
                "parameters": {
                    "flow_message_version": "3",
                    "flow_token": "token_aq_01",
                    "flow_id": FLOW_ID,
                    "flow_cta": "Get Started",
                    "flow_action": "navigate",
                    "flow_action_payload": {
                        "screen": "BASIC_INFO"
                    }
                }
            }
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    print(f"Flow send status: {response.status_code}, response: {response.text}")

def send_simple_text(recipient_id, message_body):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_id,
        "type": "text",
        "text": {"body": message_body}
    }
    requests.post(url, headers=headers, json=payload)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
