# AuntyQueen Intake: App Review kit

**App ID:** 2866362380412721
**Business portfolio:** Chifen (verified)

Status on 15 Oct 2026, from Permissions and features:

| Permission | API calls | Status |
|---|---|---|
| whatsapp_business_messaging | 1 | Ready for testing |
| whatsapp_business_management | 0 | Ready for testing; **needs at least one API call first** (video 2 makes it) |
| business_management | 0 | Ready for testing; only needed if Meta asks for it during Tech Provider onboarding |

## 1. App settings → Basic (fill before submitting)

| Field | Value |
|---|---|
| Contact email | communications@viacame.org (already set) |
| Privacy policy URL | https://aunty-queen-webhook.onrender.com/privacy (live once PR #1 is merged) |
| Data deletion instructions URL | https://aunty-queen-webhook.onrender.com/data-deletion |
| Terms of Service URL | optional; leave empty or reuse the privacy URL |
| App icon | 1024×1024 PNG of the Aunty Queen logo |
| Category | Community & government |

On Render, also set `PRIVACY_CONTACT_EMAIL = communications@viacame.org` so the policy shows the email.

## 2. Text to paste: "How will your app use this permission?"

**whatsapp_business_messaging**
> AuntyQueen Intake runs the Aunty Queen Hotline, a confidential WhatsApp hotline that gives women general,
> WHO-guideline-based sexual and reproductive health information. We use whatsapp_business_messaging to receive
> messages that people send to the hotline number and to reply with an automated intake conversation (interactive
> buttons and text). We also use it to mark messages as read, and to hand the conversation over to a human counselor
> who continues on the same number through the WhatsApp Business app (coexistence). Messages are only sent in reply to
> people who contact the hotline first. We do not send marketing messages.

**whatsapp_business_management**
> We use whatsapp_business_management to manage our own WhatsApp Business Account through Embedded Signup as a Tech
> Provider. This covers subscribing our app to the account's webhooks, reading the account's phone numbers and their
> status, creating and managing message templates for follow-up check-ins that clients ask for, and syncing contacts
> and chat history when connecting our existing WhatsApp Business app number (coexistence). Data is used only to
> operate the hotline and is never sold or shared for advertising.

## 3. Screen recording 1: message sent from the app and received in WhatsApp (about 1 minute)
You need the hotline number connected, or Meta's free **test number** from WhatsApp → API Setup, plus a second phone.

1. Show the browser at **WhatsApp → API Setup** in the AuntyQueen Intake app, with the app name visible.
2. On the second phone, send "Hi" to the number. Show the phone screen, or a mirror of it.
3. Show the bot's automatic reply arriving on the phone (the language buttons).
4. Tap **English**, and show the next message (the welcome and consent text) arriving.
5. Optional: show the row appearing in the Google Sheet.

To record on Windows, press **Win + Alt + R** (Xbox Game Bar), or use OBS. To mirror the phone screen, use Phone Link or scrcpy.

## 4. Screen recording 2: creating a message template (about 1 minute)
This also makes the first `whatsapp_business_management` API call.

1. Open **Tools → Graph API Explorer**. Select the **AuntyQueen Intake** app, and get a user token with the `whatsapp_business_management` permission.
2. Send `POST /{WABA_ID}/message_templates` with this body:
   ```json
   {
     "name": "aq_checkin",
     "language": "en",
     "category": "UTILITY",
     "components": [
       {"type": "BODY", "text": "Hello {{1}}, this is Aunty Queen checking in as you asked. Reply here if you have any questions."}
     ]
   }
   ```
   (The body text is the check-in message clients ask for at the end of the intake.)
3. Show the response with the new template ID.
4. Open **WhatsApp Manager → Message templates** and show `aq_checkin` listed as "In review" or "Active".

`WABA_ID` is shown under WhatsApp → API Setup.

## 5. Submit
App Review → Requests: request **Advanced access** for `whatsapp_business_messaging` and `whatsapp_business_management`. Paste the texts from section 2, upload the two videos, then submit.

Review usually takes a few days, and Meta may ask follow-up questions. Once both are approved, set up **Facebook Login for Business → Configurations → Embedded Signup** (see SETUP.md, step 4) and connect the Cameroon number at `/onboard`.
