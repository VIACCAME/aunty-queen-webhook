"""Coexistence onboarding: connect the existing Aunty Queen WhatsApp Business app number to this Cloud API app.

Open https://<render-url>/onboard?key=<ONBOARD_KEY> on a computer, click the button, follow Meta's popup,
and scan the QR code with the WhatsApp Business app on the hotline phone.
The page then subscribes the app to the WABA and syncs contacts + chat history (must happen within 24 hours).
"""
import hmac
import os

import requests
from flask import Blueprint, jsonify, request

onboarding = Blueprint("onboarding", __name__)

META_APP_ID = os.environ.get("META_APP_ID", "")
APP_SECRET = os.environ.get("APP_SECRET", "")
ES_CONFIG_ID = os.environ.get("ES_CONFIG_ID", "")  # Facebook Login for Business > Configurations (Embedded Signup)
ONBOARD_KEY = os.environ.get("ONBOARD_KEY", "")
GRAPH_VERSION = os.environ.get("GRAPH_VERSION", "v23.0")
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"


def key_ok():
    return bool(ONBOARD_KEY) and hmac.compare_digest(request.args.get("key", ""), ONBOARD_KEY)


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Connect Aunty Queen WhatsApp</title>
<style>
 body{font-family:system-ui,sans-serif;max-width:640px;margin:40px auto;padding:0 16px;color:#1c1c1c;background:#fff}
 button{background:#1877f2;color:#fff;border:0;border-radius:6px;padding:12px 20px;font-size:16px;cursor:pointer}
 pre{background:#f3f3f3;padding:12px;white-space:pre-wrap;word-break:break-all;border-radius:6px}
 li{margin:6px 0}
</style></head><body>
<h1>Connect Aunty Queen's WhatsApp number</h1>
<ol>
 <li>Have the hotline phone ready with the <b>latest WhatsApp Business app</b> open.</li>
 <li>Click the button and log in with the Facebook account that owns the business portfolio.</li>
 <li>Choose <b>Connect your existing WhatsApp Business app</b>, then scan the QR code with the phone.</li>
 <li>Keep the phone's WhatsApp Business app open until this page says it's finished.</li>
</ol>
<button id="go">Connect WhatsApp Business app</button>
<h3>Status</h3><pre id="out">Waiting…</pre>
<script>
 const out = document.getElementById('out');
 const log = (m) => { out.textContent += "\\n" + m; };
 let signup = null, code = null, sent = false;

 window.fbAsyncInit = function () {
   FB.init({ appId: '__APP_ID__', autoLogAppEvents: true, xfbml: true, version: '__VERSION__' });
 };
 window.addEventListener('message', (event) => {
   if (!event.origin.endsWith('facebook.com')) return;
   try {
     const data = JSON.parse(event.data);
     if (data.type === 'WA_EMBEDDED_SIGNUP') {
       log('Meta event: ' + data.event);
       if (data.event && data.event.startsWith('FINISH')) { signup = data.data; finish(); }
       if (data.event === 'CANCEL') log('Cancelled at: ' + JSON.stringify(data.data));
     }
   } catch (e) {}
 });

 async function finish() {
   if (sent || !code) return;
   // The code expires in 30 seconds; give the signup event a moment to arrive.
   for (let i = 0; i < 10 && !signup; i++) await new Promise(r => setTimeout(r, 500));
   sent = true;
   log('Finishing setup on the server…');
   const r = await fetch(location.pathname + '/complete' + location.search, {
     method: 'POST', headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({ code, ...(signup || {}) })
   });
   const j = await r.json();
   log(JSON.stringify(j, null, 2));
   if (j.access_token) {
     log('\\nDONE. In Render > Environment set:\\nWHATSAPP_TOKEN = the access_token above\\nPHONE_NUMBER_ID = ' + j.phone_number_id + '\\nThen close this page.');
   }
 }

 document.getElementById('go').onclick = () => {
   FB.login((response) => {
     if (response.authResponse && response.authResponse.code) {
       code = response.authResponse.code; log('Got authorization code.'); finish();
     } else { log('Login was not completed.'); }
   }, {
     config_id: '__CONFIG_ID__',
     response_type: 'code',
     override_default_response_type: true,
     extras: { setup: {}, featureType: 'whatsapp_business_app_onboarding', sessionInfoVersion: '3' }
   });
 };
</script>
<script async defer crossorigin="anonymous" src="https://connect.facebook.net/en_US/sdk.js"></script>
</body></html>"""


@onboarding.route("/onboard", methods=["GET"])
def onboard_page():
    if not key_ok():
        return "Forbidden", 403
    html = (PAGE.replace("__APP_ID__", META_APP_ID)
                .replace("__VERSION__", GRAPH_VERSION)
                .replace("__CONFIG_ID__", ES_CONFIG_ID))
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@onboarding.route("/onboard/complete", methods=["POST"])
def onboard_complete():
    if not key_ok():
        return "Forbidden", 403
    body = request.get_json(silent=True) or {}
    steps = {}

    # 1. Exchange the 30-second code for a business token.
    r = requests.get(f"{GRAPH}/oauth/access_token", params={
        "client_id": META_APP_ID, "client_secret": APP_SECRET, "code": body.get("code", "")
    }, timeout=20)
    token = r.json().get("access_token")
    if not token:
        return jsonify({"error": "token exchange failed", "meta": r.json()}), 400
    auth = {"Authorization": f"Bearer {token}"}

    waba_id = body.get("waba_id")
    if not waba_id:
        return jsonify({"error": "no waba_id received from Meta; check the Status log", "access_token": token}), 400

    # 2. Subscribe this app to the WABA's webhooks (without this, no messages arrive).
    steps["subscribe_app"] = requests.post(f"{GRAPH}/{waba_id}/subscribed_apps", headers=auth, timeout=20).json()

    # 3. Find the phone number ID (the coexistence event only sends the WABA ID).
    phone_number_id = body.get("phone_number_id")
    if not phone_number_id:
        nums = requests.get(f"{GRAPH}/{waba_id}/phone_numbers", headers=auth, timeout=20).json().get("data", [])
        steps["phone_numbers"] = [{"id": n.get("id"), "number": n.get("display_phone_number")} for n in nums]
        phone_number_id = nums[0]["id"] if nums else None

    if phone_number_id:
        steps["number_status"] = requests.get(
            f"{GRAPH}/{phone_number_id}", headers=auth,
            params={"fields": "display_phone_number,is_on_biz_app,platform_type"}, timeout=20).json()
        # 4. Sync contacts, then chat history. Each can run once, within 24 hours of onboarding.
        # The number is already registered by the app, so do NOT call /register.
        for sync_type in ("smb_app_state_sync", "history"):
            steps[f"sync_{sync_type}"] = requests.post(
                f"{GRAPH}/{phone_number_id}/smb_app_data", headers=auth,
                json={"messaging_product": "whatsapp", "sync_type": sync_type}, timeout=30).json()

    return jsonify({
        "waba_id": waba_id,
        "phone_number_id": phone_number_id,
        "access_token": token,
        "steps": steps,
    })
