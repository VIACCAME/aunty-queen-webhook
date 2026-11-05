# Aunty Queen Hotline: setup

How it works:

1. A client messages Aunty Queen's Cameroon number. The bot (this app on Render) runs the intake.
2. **Side questions** typed during the intake are answered by a free AI, using only the hotline's own WHO-based information. The bot then re-asks the question it was on, until every intake question is answered.
3. **Warning signs** (for example "I'm bleeding a lot") → the bot sends the "go to a health facility" message and marks the row `URGENT`. **"I want to talk to a person"** → a counselor takes over.
4. Every answer is saved right away to the **Intakes** tab of a Google Sheet.
5. When the intake ends, or there's an urgent case, a request for a person, or more than `AI_MAX_QUESTIONS` side questions, the bot **and the AI switch off** for that client.
6. Counselors reply from the **WhatsApp Business app on the hotline phone** (coexistence).
   - If a counselor replies at any point, the bot stops for that client straight away.
   - To give a chat back to the bot, the counselor sends `#bot` in that chat.

## 1. Free AI key (Groq, about 2 minutes)
1. Sign up at console.groq.com.
2. Go to **API Keys → Create** and copy the key.

The free tier has rate limits, which is plenty for a hotline. According to Groq's policy, API data is not used for training; check this yourself before going live.

Gemini's free tier is **not** recommended here, because Google may use free-tier data to improve its products. Any OpenAI-compatible API works if you change `AI_BASE_URL` and `AI_MODEL`.

Only the client's message and the current question are sent to the AI. The phone number and name are not.

## 2. Google Sheet (about 10 minutes)
1. Create a new Google Sheet. Share it **only** with counselors, because it holds health data.
2. Go to **Extensions → Apps Script**, paste in `google_apps_script.gs` and save.
3. Go to **Project Settings → Script properties** and add `SHEET_SECRET` with a long random value.
4. Go to **Deploy → New deployment → Web app**. Set Execute as **Me** and Who has access **Anyone**, then click Deploy.
5. Copy the `/exec` URL.

To download the data, use **File → Download → Excel or CSV**.

## 3. Render (service `aunty-queen-webhook`)
Under **Environment**, set these variables:

| Key | Value |
|---|---|
| `VERIFY_TOKEN` | a new random string; you'll type the same value in Meta |
| `APP_SECRET` | Meta App → App settings → Basic → App secret |
| `META_APP_ID` | `2866362380412721` |
| `ES_CONFIG_ID` | the Embedded Signup configuration ID (from step 4) |
| `ONBOARD_KEY` | a random string that protects the `/onboard` page |
| `GOOGLE_SHEET_WEBHOOK_URL` | the `/exec` URL from step 2 |
| `SHEET_SECRET` | the same value you used in the Apps Script |
| `AI_API_KEY` | the Groq key from step 1 |
| `WHATSAPP_TOKEN`, `PHONE_NUMBER_ID` | shown by the `/onboard` page at the end of step 5 |

Under **Settings → Start Command**, set:
`gunicorn app:app --workers 1 --threads 8 --timeout 60`

**Plan:** free instances go to sleep and take about 50 seconds to wake up. For a live hotline, use **Starter**.

## 4. Make the AuntyQueen Intake app a Tech Provider
Do this in the App Dashboard → WhatsApp use case → **Tech Provider onboarding**.

1. **Business verification** of the business portfolio, using the business's legal documents.
2. **App settings:** app icon, privacy policy URL, category.
3. **App Review:** request **advanced access** for `whatsapp_business_messaging` and `whatsapp_business_management`. Meta asks for two screen recordings:
   - one showing a message sent from the app and received on WhatsApp
   - one showing a message template being created
4. **Facebook Login for Business → Configurations → Create:**
   - Login variation: **Embedded Signup**
   - Product: **WhatsApp Cloud API**
   - Copy the **configuration ID** into `ES_CONFIG_ID`.
5. **Allowed domains:** in Facebook Login for Business → Settings, add the Render domain to the allowed domains and to the valid OAuth redirect URIs.

## 5. Connect the existing Cameroon number (coexistence)
Requirements:
- The hotline phone has the **latest WhatsApp Business app**.
- The number has been in active use on the app for **7 days or more**.
- The phone has a working camera, to scan the QR code.

Don't delete or re-register the number on the app.

Steps:
1. Open `https://<render-url>/onboard?key=<ONBOARD_KEY>` on a computer, with the hotline phone next to you.
2. Click **Connect**, log in, choose **Connect your existing WhatsApp Business app**, and scan the QR code with the phone.
3. The page subscribes the app to the WABA and syncs contacts and history. This has to happen **within 24 hours** of connecting.
4. The page then shows `access_token` and `phone_number_id`. Paste them into Render as `WHATSAPP_TOKEN` and `PHONE_NUMBER_ID`.
5. In App Dashboard → WhatsApp → **Configuration**:
   - Callback URL: `https://<render-url>/webhook`
   - Verify token: your `VERIFY_TOKEN`
   - Subscribe to **messages**, **smb_message_echoes**, **history** and **smb_app_state_sync**.
6. Set the app to **Live**.

Things that change on the phone after connecting:
- Broadcast lists become read-only.
- Disappearing messages and view-once are off for 1:1 chats.
- Calls and chats on the phone keep working.

## 6. Test
1. Message the number from a phone that isn't on the team, and ask a side question during the intake. The AI should answer, and then the bot should repeat the question it was on.
2. Check that a row appears in **Intakes**.
3. Reply from the Business app and check that the bot goes quiet.
4. Send `#bot` and check that the next message restarts the intake.

## Alternative: send through Infobip instead of Meta directly
Use this if Meta blocks step 5 ("… can't onboard customers right now"). Infobip is an approved Meta partner, so its own signup flow can connect the number with coexistence. Code: `infobip.py`.

Counselor replies from the WhatsApp Business app reach the bot through Infobip's **"Business app message echo"** event. Its payload format isn't in Infobip's public API reference, so the bot recognises an echo either by coming from the hotline number or by an "echo" marker, and logs the field names of every echo and every unrecognised message. **After the first counselor reply, check the Render logs** for `[Infobip] staff echo` and confirm the bot went quiet.

Steps:
1. Sign up at infobip.com (free trial: 60 days, 100 conversations, verified test numbers only).
2. **Test with a spare number first, not the hotline.** A number connected through Infobip is tied to Infobip until you disconnect it there.
3. Connect the number: Channels → WhatsApp → Senders → add sender → connect an existing WhatsApp Business app number. Choose **"Don't share chats"**.
4. Go to **Developer Tools → Subscriptions Management → Create subscription**:
   - Channel: **WhatsApp**
   - Events: **Inbound message** and **Business app message echo**
   - Filtering: the hotline number
   - Notification profile: webhook URL `https://<render-url>/infobip/webhook?key=<INFOBIP_WEBHOOK_KEY>`
   Then check that Numbers → the hotline → WhatsApp → Inbound configuration no longer says "Subscription missing".
5. In Render → Environment, set:

| Key | Value |
|---|---|
| `WHATSAPP_PROVIDER` | `infobip` (remove it, or set `meta`, to go back to Meta) |
| `INFOBIP_BASE_URL` | your personal API base URL, shown on the Infobip portal home page, e.g. `abcd12.api.infobip.com` |
| `INFOBIP_API_KEY` | portal → Developers → API keys → create |
| `INFOBIP_SENDER` | the WhatsApp number, digits only, e.g. `2376…` |
| `INFOBIP_WEBHOOK_KEY` | a new random string, the same one used in the URL in step 4 |

6. Run the tests in section 6. Test 3 (counselor reply) is the one most likely to fail.

## Wording and languages
All bot texts, in English and French, are in `messages.py`. Edit the wording there; keep the medical facts (doses, timings, warning signs) exactly as in the protocol. The French texts use "tu" and **need review by the team** before going live.

## Database, dashboard and broadcast
**Database = the private Google Sheet** (step 2). After pasting the new `google_apps_script.gs`, redeploy it:
Deploy → Manage deployments → Edit (pencil) → Version: **New version** → Deploy. The `/exec` URL stays the same.
Tabs it fills in by itself:
- **Intakes**: one row per conversation, with an AI **summary** for counselors when it ends
- **Contacts**: one row per person (profile, first and last contact, STOP opt-out, last broadcast)
- **Messages**: every message in and out (client, bot, counselor), with time
- **Imported**: rows uploaded from old Excel/CSV files

Render → Environment:

| Key | Value |
|---|---|
| `GOOGLE_SHEET_WEBHOOK_URL` | the Apps Script `/exec` URL |
| `SHEET_SECRET` | same value as the Script property |
| `DASHBOARD_KEY` | a long password for the dashboard |
| `BROADCAST_TEMPLATE` | (optional) the approved template name, pre-filled on the dashboard |
| `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL` | the AI (see `ai.py` for Gemini values) |

**Dashboard:** `https://<render-url>/dashboard`. Stats, pill requests with summaries, chat history per person,
Excel/CSV import, and the broadcast. Don't share screenshots: it shows health data.

**Returning clients** get "welcome back" and skip the questions they already answered.
**Counselor replies** pause the bot for that chat until a counselor sends `#bot`.
**STOP** (or *arrêter*) opts a person out of broadcasts.

**Broadcast template** (create in Infobip → Channels → WhatsApp → Templates, category *Utility* or *Marketing*,
one per language; Meta approves it in about a day). Keep it neutral, it may be seen by someone else:
- English, name `aunty_queen_checkin`: *Hello from Aunty Queen 💛 We're checking in with friends who wrote to us before. Reply HI to chat with us, or STOP if you'd rather not hear from us.*
- French, same name, language French: *Bonjour de la part d'Aunty Queen 💛 Nous prenons des nouvelles des personnes qui nous ont écrit. Réponds HI pour discuter avec nous, ou STOP si tu préfères ne plus recevoir de messages.*

The dashboard only sends to people who didn't reply STOP, haven't written in the last 7 days and
got no broadcast in the last 30 days. Each template message costs about US$0.036 (marketing) or $0.006 (utility).

## Not done yet
- **French review:** a French-speaking counselor should read every French text in `messages.py`.
