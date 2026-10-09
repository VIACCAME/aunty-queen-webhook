import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "aunty_queen_secret_123")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
GOOGLE_SHEET_WEBHOOK_URL = os.environ.get("GOOGLE_SHEET_WEBHOOK_URL")

# Persistent memory dictionary across the conversation
sessions = {}

def get_graph_url():
    return f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"

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

@app.route("/", methods=["GET"])
def home():
    return "Aunty Queen Hotline Full Bot Active", 200

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

        # Initialize session state for user
        if sender_id not in sessions:
            sessions[sender_id] = {
                "step": "STAGE_1_START",
                "lang": "en",
                "name": "Friend",
                "confirmation_method": "",
                "lmp": "",
                "preference": "",
                "health_issues": "",
                "support_person": "",
                "pill_choice": "",
                "followup_time": ""
            }

        session = sessions[sender_id]

        # Extract text or button clicks
        user_input = ""
        button_id = ""

        if msg_type == "text":
            user_input = msg.get("text", {}).get("body", "").strip()
        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            if interactive.get("type") == "button_reply":
                button_id = interactive["button_reply"]["id"]
                user_input = interactive["button_reply"]["title"]

        step = session["step"]
        name = session.get("name", "Friend")

        # =====================================================================
        # STAGE 0: LANGUAGE SELECTION
        # =====================================================================
        if step == "STAGE_1_START":
            send_buttons(
                sender_id,
                body_text="Hello, and welcome to Aunty Queen Hotline.\nPlease select your language / Choisissez votre langue :",
                buttons=[
                    {"id": "lang_en", "title": "English"},
                    {"id": "lang_fr", "title": "Français"}
                ],
                footer_text="Aunty Queen Hotline"
            )
            session["step"] = "STAGE_1_CONSENT"

        # =====================================================================
        # STAGE 1: WELCOME & CONSENT (1.1, 1.2, 1.3)
        # =====================================================================
        elif step == "STAGE_1_CONSENT":
            session["lang"] = "fr" if (button_id == "lang_fr" or "fr" in user_input.lower()) else "en"

            welcome_body = (
                "Hello, and welcome to Aunty Queen Hotline.\n"
                "We share general information on sexual and reproductive health, including safe abortion information based on World Health Organization guidelines.\n\n"
                "🔒 *Confidentiality and chat safety:*\n"
                "Everything shared in this chat is kept confidential. It is used only for our own records.\n"
                "To keep this chat private on the phone, many women turn on disappearing messages or delete the chat when we finish.\n\n"
                "To support you well, we will need to ask a few personal questions. Would that be OK?"
            )
            send_buttons(
                sender_id,
                body_text=welcome_body,
                buttons=[
                    {"id": "c_ok", "title": "Yes, that is OK"},
                    {"id": "c_what", "title": "What will you ask?"}
                ]
            )
            session["step"] = "STAGE_1_NAME"

        elif step == "STAGE_1_NAME":
            if button_id == "c_what" or "what" in user_input.lower():
                # 1.3a What we ask
                explain = (
                    "*What we ask:*\n"
                    "We ask about: age, date of last period, education, number of pregnancies and children, "
                    "reason for reaching out, and whether someone is supporting you.\n\n"
                    "Any question can be skipped.\n\n"
                    "And what name would you like us to call you?"
                )
                send_text(sender_id, explain)
            else:
                send_text(sender_id, "Thank you. And what name would you like us to call you?")
            session["step"] = "STAGE_1_HOW_CAN_WE_HELP"

        elif step == "STAGE_1_HOW_CAN_WE_HELP":
            name = user_input if user_input else "Friend"
            session["name"] = name

            help_msg = (
                f"Thank you, {name}.\n\n"
                "How can we support you today? Please reply with the number:\n"
                "1. Information about safe abortion with pills\n"
                "2. I have already used the pills and have questions\n"
                "3. Information about contraception\n"
                "4. Something else"
            )
            send_text(sender_id, help_msg)
            session["step"] = "STAGE_1_HELP_ROUTING"

        elif step == "STAGE_1_HELP_ROUTING":
            if "1" in user_input or "safe" in user_input.lower():
                # 1.5 What the hotline offers
                offer_text = (
                    f"We will do our best to support you, {name}.\n\n"
                    "Aunty Queen shares scientific information about safe self-managed abortion with pills, "
                    "for pregnancies up to 12 weeks. We can also give information about manual vacuum aspiration (MVA), which is done in a clinic.\n\n"
                    "An abortion with pills causes the same process as a miscarriage.\n\n"
                    "Would you like information about safe abortion with pills?"
                )
                send_buttons(
                    sender_id,
                    body_text=offer_text,
                    buttons=[
                        {"id": "pills_yes", "title": "Yes"},
                        {"id": "pills_no", "title": "No"}
                    ]
                )
                session["step"] = "STAGE_2_PREGNANCY_CONFIRM"

            elif "2" in user_input:
                # Direct route to Stage 5 warning signs
                send_stage_5_warning_check(sender_id, name)
                session["step"] = "STAGE_5_TRIAGE"

            elif "3" in user_input:
                # Direct route to Stage 6.3 contraception
                send_stage_6_3_contraception(sender_id, name)
                session["step"] = "STAGE_6_CONTRACEPTION_CHOICE"

            else:
                send_text(sender_id, f"Please explain in your own words how we can assist you, {name}. A counselor will reply to you directly.")
                session["step"] = "HANDOFF_TO_HUMAN"

        # =====================================================================
        # STAGE 2: UNDERSTANDING HER SITUATION
        # =====================================================================
        elif step == "STAGE_2_PREGNANCY_CONFIRM":
            # 2.1 How the pregnancy was confirmed
            q_text = f"Can you tell us how the pregnancy was confirmed, {name}?"
            send_buttons(
                sender_id,
                body_text=q_text,
                buttons=[
                    {"id": "conf_test", "title": "Pregnancy test"},
                    {"id": "conf_scan", "title": "Ultrasound (scan)"},
                    {"id": "conf_missed", "title": "Missed period only"}
                ]
            )
            session["step"] = "STAGE_2_LMP"

        elif step == "STAGE_2_LMP":
            session["confirmation_method"] = user_input
            if button_id == "conf_scan" or "ultrasound" in user_input.lower() or "scan" in user_input.lower():
                send_text(sender_id, "What did the scan result say, and how many weeks? Also, what was the first day of your last menstrual period (an approximate date is fine)?")
            else:
                # 2.2 Length of pregnancy
                send_text(sender_id, "What was the first day of the last menstrual period? An approximate date is fine.")
            session["step"] = "STAGE_2_PREFERENCE"

        elif step == "STAGE_2_PREFERENCE":
            session["lmp"] = user_input
            # 2.3 Preference: pills or clinic procedure
            pref_text = (
                f"Some women prefer abortion with pills at home. Others prefer MVA, a short procedure in a clinic. "
                f"Do you already know which one you prefer, {name}?"
            )
            send_buttons(
                sender_id,
                body_text=pref_text,
                buttons=[
                    {"id": "pref_pills", "title": "Pills"},
                    {"id": "pref_mva", "title": "MVA in a clinic"},
                    {"id": "pref_both", "title": "Hear about both"}
                ]
            )
            session["step"] = "STAGE_2_HEALTH"

        elif step == "STAGE_2_HEALTH":
            session["preference"] = user_input
            # 2.4 Health questions
            health_text = (
                f"Can we ask a few health questions, {name}?\n\n"
                "- Do you have any health problems or allergies?\n"
                "- Are you taking any medication?\n"
                "- Do you have an IUD (coil)?"
            )
            send_buttons(
                sender_id,
                body_text=health_text,
                buttons=[
                    {"id": "health_no", "title": "No to all"},
                    {"id": "health_yes", "title": "I have some"}
                ]
            )
            session["step"] = "STAGE_2_HEALTH_DETAILS"

        elif step == "STAGE_2_HEALTH_DETAILS":
            if button_id == "health_yes" or "yes" in user_input.lower():
                # 2.4a If health problem reported
                note = (
                    "Thank you for telling us. An early abortion with pills is safer than continuing a pregnancy and giving birth, "
                    "and for some health conditions pregnancy can make the condition worse.\n\n"
                    "Women with health problems can still use the pills. They are advised to have someone with them and to be near medical care in case of a complication.\n\n"
                    "Please briefly mention any specific condition, medication, or if you have an IUD:"
                )
                send_text(sender_id, note)
                session["step"] = "STAGE_2_SUPPORT"
            else:
                session["health_issues"] = "None reported"
                send_stage_2_support(sender_id, name)
                session["step"] = "STAGE_2_DECISION"

        elif step == "STAGE_2_SUPPORT":
            session["health_issues"] = user_input
            send_stage_2_support(sender_id, name)
            session["step"] = "STAGE_2_DECISION"

        elif step == "STAGE_2_DECISION":
            session["support_person"] = user_input
            # 2.6 Her decision
            decision_msg = (
                f"Can we ask about your decision, {name}? It is important that this choice is yours, made without pressure from anyone.\n\n"
                "You are the only person who can judge your situation and make the best choice for your life.\n\n"
                "Are you comfortable continuing to information on what is needed?"
            )
            send_buttons(
                sender_id,
                body_text=decision_msg,
                buttons=[
                    {"id": "dec_continue", "title": "Yes, continue"},
                    {"id": "dec_questions", "title": "I have questions"}
                ]
            )
            session["step"] = "STAGE_3_BEFORE"

        # =====================================================================
        # STAGE 3: BEFORE THE ABORTION
        # =====================================================================
        elif step == "STAGE_3_BEFORE":
            # 3.1 & 3.2 What is needed
            pills_needed = (
                "Research shows two effective methods:\n"
                "1. *Mifepristone with misoprostol*: 1 mifepristone tablet (200 mg) and 4 misoprostol tablets (200 mcg each)\n"
                "2. *Misoprostol alone*: 12 misoprostol tablets (200 mcg each)\n\n"
                "Where to get pills: A counselor can discuss safe access options confidentially."
            )
            send_text(sender_id, pills_needed)

            # 3.3 & 3.4 Planning and readiness
            plan_text = (
                "While getting the pills, you can start making a plan for the day:\n"
                "- Someone to give emotional support\n"
                "- Childcare and other tasks arranged\n"
                "- A time and place free of stress, ideally with a private bathroom\n"
                "- Painkillers such as ibuprofen 400-600 mg ready in advance\n"
                "- Think in advance about where to go if extra care is needed.\n\n"
                "Do you have any questions so far?"
            )
            send_buttons(
                sender_id,
                body_text=plan_text,
                buttons=[
                    {"id": "plan_ready", "title": "Ready for steps"},
                    {"id": "plan_ask", "title": "I have a question"}
                ]
            )
            session["step"] = "STAGE_4_METHOD_CHOICE"

        # =====================================================================
        # STAGE 4: USING THE PILLS
        # =====================================================================
        elif step == "STAGE_4_METHOD_CHOICE":
            # 4.1 & Method selection
            method_select = (
                "The next messages explain how the pills are used. It helps to have a pen and paper to write the steps down.\n\n"
                "Which pills will you be using?"
            )
            send_buttons(
                sender_id,
                body_text=method_select,
                buttons=[
                    {"id": "m_miso_only", "title": "Misoprostol alone"},
                    {"id": "m_combo", "title": "Mife + Misoprostol"}
                ]
            )
            session["step"] = "STAGE_4_STEPS_DELIVERY"

        elif step == "STAGE_4_STEPS_DELIVERY":
            if button_id == "m_combo" or "mife" in user_input.lower():
                session["pill_choice"] = "Mifepristone + Misoprostol"
                steps_text = (
                    "*How to take Mifepristone with Misoprostol (1 + 4 pills):*\n\n"
                    "Step 1: Swallow 1 mifepristone tablet (200 mg) with a glass of water.\n\n"
                    "Step 2: 24 hours later, put 4 misoprostol pills (200 mcg each) between the gum and cheek (2 on left, 2 on right). "
                    "Leave them there for 30 minutes to dissolve. After 30 minutes, swallow whatever remains."
                )
            else:
                session["pill_choice"] = "Misoprostol alone"
                steps_text = (
                    "*How to take Misoprostol alone (12 pills total):*\n"
                    "The most effective way is to put 4 pills under the tongue every 3 hours, 3 times.\n\n"
                    "Step 1: Put 4 pills under the tongue. Do not swallow for 30 minutes while they dissolve. After 30 mins, swallow what is left.\n"
                    "Step 2: 3 hours later, put another 4 pills under the tongue for 30 minutes.\n"
                    "Step 3: 3 hours later, put the last 4 pills under the tongue for 30 minutes."
                )
            send_text(sender_id, steps_text)

            # 4.3 Eating/drinking & 4.5 - 4.7 Symptoms
            effects_text = (
                "📌 *Important rules & what to expect:*\n"
                "- Do not eat or drink during the 30 minutes while pills are dissolving. Normal eating/drinking before and after is fine.\n"
                "- Normal side effects: cramps, chills, mild fever, nausea, diarrhea.\n"
                "- Bleeding usually starts 2 to 4 hours after misoprostol. Heaviest bleeding lasts 1 to 4 hours with clots, then eases.\n"
                "- Pain relief: Ibuprofen 600 mg can be taken after the first misoprostol dose.\n\n"
                "Can you tell us, in your own words, how the pills are taken? Do you have any doubts?"
            )
            send_text(sender_id, effects_text)
            session["step"] = "STAGE_5_EXPLANATION"

        # =====================================================================
        # STAGE 5: SIGNS OF COMPLICATION
        # =====================================================================
        elif step == "STAGE_5_EXPLANATION":
            # 5.1, 5.2, 5.3 The four warning signs
            warning_signs_full = (
                "Thank you. Now, here are the *4 Warning Signs of Complication* to always remember:\n\n"
                "1. *Too much bleeding*: soaking more than 2 maxi pads per hour for 2 or 3 consecutive hours, or bleeding like an open tap.\n"
                "2. *Severe pain* that painkillers do not relieve.\n"
                "3. *Bad-smelling* vaginal discharge.\n"
                "4. *Fever* over 38°C for more than 24 hours, or over 39°C at any time.\n\n"
                "🏥 *Getting care*: Any complication is treated exactly like a miscarriage. A woman can always go to any clinic and say she had a miscarriage."
            )
            send_text(sender_id, warning_signs_full)

            # 5.4 Check understanding
            send_buttons(
                sender_id,
                body_text="Are the 4 warning signs clear to you?",
                buttons=[
                    {"id": "warn_clear", "title": "Yes, all clear"},
                    {"id": "warn_repeat", "title": "Please repeat"}
                ]
            )
            session["step"] = "STAGE_6_AFTERCARE"

        # =====================================================================
        # STAGE 6: AFTER THE ABORTION & CONTRACEPTION
        # =====================================================================
        elif step == "STAGE_6_AFTERCARE":
            aftercare_info = (
                "📌 *After the abortion:*\n"
                "- Bleeding decreases gradually and can continue 1 to 3 weeks.\n"
                "- Normal period usually returns in 4 to 6 weeks.\n"
                "- Precaution: Do not put anything in the vagina (no sex, tampons, baths) for the first 2 to 3 days.\n"
                "- Confirming success: Take a pregnancy test in 3 to 4 weeks (a test done earlier can show a false positive).\n\n"
                "You can get pregnant again immediately after an abortion.\n"
                "Would you like information about contraception?"
            )
            send_buttons(
                sender_id,
                body_text=aftercare_info,
                buttons=[
                    {"id": "contra_yes", "title": "Yes"},
                    {"id": "contra_no", "title": "No, thank you"}
                ]
            )
            session["step"] = "STAGE_6_CONTRACEPTION_CHOICE"

        elif step == "STAGE_6_CONTRACEPTION_CHOICE":
            if button_id == "contra_yes" or "yes" in user_input.lower():
                send_stage_6_3_contraception(sender_id, name)
                session["step"] = "STAGE_7_CLOSING"
            else:
                send_stage_7_closing(sender_id, name)
                session["step"] = "STAGE_7_CHECKIN_TIME"

        # =====================================================================
        # STAGE 7: CLOSING AND FOLLOW-UP
        # =====================================================================
        elif step == "STAGE_7_CLOSING":
            send_stage_7_closing(sender_id, name)
            session["step"] = "STAGE_7_CHECKIN_TIME"

        elif step == "STAGE_7_CHECKIN_TIME":
            session["followup_time"] = user_input
            closing_farewell = (
                f"Thank you, {name}. We have noted that. "
                "You can always write to Aunty Queen again whenever you have questions or worries. "
                "We wish you the very best. Take good care.\n\n"
                "— *A counselor is available here if you need any further human support.*"
            )
            send_text(sender_id, closing_farewell)

            # Log complete intake session to Google Sheets
            save_to_google_sheets({
                "phone": sender_id,
                "name": name,
                "language": session.get("lang"),
                "category": "Full Abortion Information Flow",
                "confirmation_method": session.get("confirmation_method"),
                "lmp": session.get("lmp"),
                "preference": session.get("preference"),
                "health_issues": session.get("health_issues"),
                "support_person": session.get("support_person"),
                "pill_choice": session.get("pill_choice"),
                "followup_time": session.get("followup_time")
            })
            session["step"] = "HANDOFF_TO_HUMAN"

        # Direct triage responses if user came from option 2
        elif step == "STAGE_5_TRIAGE":
            if button_id == "warn_report_yes" or "yes" in user_input.lower():
                # Quick reply: Warning sign reported
                emergency_text = (
                    "🚨 *What you describe is one of the signs that needs medical care.*\n\n"
                    "Please go to the nearest health facility now. The treatment is the same as for a miscarriage, "
                    "and a woman can say she had a miscarriage. Message us when you can; we are here."
                )
                send_text(sender_id, emergency_text)
            else:
                send_text(sender_id, f"Thank you for confirming, {name}. A counselor will review your symptoms with you directly.")
            session["step"] = "HANDOFF_TO_HUMAN"

        elif step == "HANDOFF_TO_HUMAN":
            # Handover active: the bot stays quiet so your team can speak
            pass

    except Exception as e:
        print(f"[ERROR in receive_message]: {e}")

    return jsonify({"status": "success"}), 200

# Helper routines for reusable blocks
def send_stage_2_support(sender_id, name):
    supp_text = (
        f"The risk of complications is very low, but it can help to have someone for emotional support.\n\n"
        f"Is there someone who can be with you during the abortion, and someone you can talk to about it, {name}?"
    )
    send_buttons(
        sender_id,
        body_text=supp_text,
        buttons=[
            {"id": "supp_yes", "title": "Yes, I have support"},
            {"id": "supp_no", "title": "No, I am alone"}
        ]
    )

def send_stage_5_warning_check(sender_id, name):
    w_body = (
        f"{name}, are you experiencing any of these 4 warning signs right now?\n"
        "1. Soaking 2+ pads/hour for 2 hours\n"
        "2. Severe pain unrelieved by painkillers\n"
        "3. Bad-smelling vaginal discharge\n"
        "4. Fever over 38°C"
    )
    send_buttons(
        sender_id,
        body_text=w_body,
        buttons=[
            {"id": "warn_report_yes", "title": "Yes, I have them"},
            {"id": "warn_report_no", "title": "No, I do not"}
        ]
    )

def send_stage_6_3_contraception(sender_id, name):
    c_msg = (
        f"*Contraception Methods (6.3a):*\n\n"
        "- *Pill, patch, injection, implant*: Can be started up to 5 days after taking misoprostol and protect immediately.\n"
        "- *Vaginal ring*: Can be inserted as soon as 2 or 3 days after misoprostol.\n"
        "- *IUD*: Inserted once complete abortion is confirmed, or during the next period.\n"
        "- *Condoms, barrier methods*: Can be used as soon as sex is resumed.\n"
        "- *Fertility awareness*: Once regular cycles return."
    )
    send_text(sender_id, c_msg)

def send_stage_7_closing(sender_id, name):
    closing = (
        f"Do you have any other question or concern, {name}?\n\n"
        "Would you like us to check in with you later? If yes, please tell us which day and time is safe to message."
    )
    send_text(sender_id, closing)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
