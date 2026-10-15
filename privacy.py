"""Public privacy policy page (required by Meta App Review): https://<render-url>/privacy"""
import html
import os

from flask import Blueprint

privacy = Blueprint("privacy", __name__)

ORG_NAME = os.environ.get("ORG_NAME", "Aunty Queen Hotline")
CONTACT_EMAIL = os.environ.get("PRIVACY_CONTACT_EMAIL", "")
LAST_UPDATED = "15 October 2026"


@privacy.route("/data-deletion", methods=["GET"])
def data_deletion_page():
    org = html.escape(ORG_NAME)
    contact = (f' You can also email <a href="mailto:{html.escape(CONTACT_EMAIL)}">{html.escape(CONTACT_EMAIL)}</a>.'
               if CONTACT_EMAIL else "")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Data Deletion · {org}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 16px;line-height:1.6;color:#1c1c1c;background:#fff}}</style>
</head><body>
<h1>How to delete your data</h1>
<p><b>{org}</b></p>
<ol>
 <li>Send the word <b>DELETE</b> to the hotline on WhatsApp, from the number you used to contact us.</li>
 <li>A counselor will delete your intake records and conversation notes, and confirm in the chat.</li>
 <li>You can also delete the chat on your own phone at any time.</li>
</ol>
<p>{contact}</p>
<p>See our full <a href="/privacy">privacy policy</a>.</p>
</body></html>"""
    return page, 200, {"Content-Type": "text/html; charset=utf-8"}


@privacy.route("/privacy", methods=["GET"])
def privacy_page():
    org = html.escape(ORG_NAME)
    contact = (f'by email at <a href="mailto:{html.escape(CONTACT_EMAIL)}">{html.escape(CONTACT_EMAIL)}</a> or '
               if CONTACT_EMAIL else "")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Privacy Policy · {org}</title>
<style>
 body{{font-family:system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 16px;line-height:1.6;color:#1c1c1c;background:#fff}}
 h1{{font-size:1.8em}} h2{{font-size:1.2em;margin-top:2em}}
</style></head><body>
<h1>Privacy Policy</h1>
<p><b>{org}</b> · Last updated {LAST_UPDATED}</p>

<p>{org} is a confidential WhatsApp hotline that shares general information on sexual and reproductive health,
based on World Health Organization guidelines. This policy explains what we collect when you message us,
why, and how you can ask us to delete it.</p>

<h2>What we collect</h2>
<ul>
 <li>Your WhatsApp phone number and the messages you send us.</li>
 <li>The answers you choose to give during our intake questions (for example the name you want us to use,
     the date of your last period, health information you share, and when it is safe to contact you).
     Every question can be skipped.</li>
</ul>

<h2>Why we use it</h2>
<ul>
 <li>To answer you and give you the information you ask for.</li>
 <li>So a trained counselor can continue the conversation with you.</li>
 <li>For our own internal records, to improve the support we give. We never sell your information or use it
     for advertising.</li>
</ul>

<h2>Who processes it</h2>
<ul>
 <li><b>Meta / WhatsApp</b> delivers the messages (WhatsApp Business Platform).</li>
 <li><b>Render</b> hosts the software that runs our automated assistant.</li>
 <li><b>Google</b> (Google Sheets) stores intake records, which only our counselors can access.</li>
 <li>An <b>AI language service</b> may receive the text of a question you type, without your phone number or
     name, so the assistant can answer it.</li>
</ul>

<h2>How long we keep it</h2>
<p>We keep intake records only as long as needed to support you and for our internal records, and delete
them on request.</p>

<h2 id="data-deletion">Deleting your data</h2>
<p>You can ask us at any time to delete your information. Message the hotline on WhatsApp with the word
<b>DELETE</b>, or contact us {contact}through the hotline, and a counselor will delete your records and confirm.
You can also delete the chat on your own phone at any time.</p>

<h2>Keeping your chat private</h2>
<p>To keep this chat private on your phone, you can turn on disappearing messages or delete the chat when we
finish.</p>

<h2>Changes</h2>
<p>If we change this policy we will update the date above.</p>
</body></html>"""
    return page, 200, {"Content-Type": "text/html; charset=utf-8"}
