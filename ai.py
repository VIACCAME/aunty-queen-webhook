"""Free-text helper: answers side questions during the intake, then the bot re-asks the current question.

Uses any OpenAI-compatible chat API. Default is Groq's free tier.
Only the client's message and the current question are sent. No phone number or name.
"""
import json
import os

import requests

AI_API_KEY = os.environ.get("AI_API_KEY")
AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
AI_MODEL = os.environ.get("AI_MODEL", "llama-3.3-70b-versatile")

KNOWLEDGE = """
Aunty Queen Hotline shares general information on sexual and reproductive health, including safe abortion
information based on World Health Organization (WHO) guidelines. Everything shared is confidential.

Safe abortion with pills (up to 12 weeks of pregnancy). It causes the same process as a miscarriage.
- Method 1, mifepristone + misoprostol: swallow 1 mifepristone tablet (200 mg) with water. 24 hours later put
  4 misoprostol tablets (200 mcg each) between gum and cheek (2 each side) for 30 minutes, then swallow what remains.
- Method 2, misoprostol alone (12 tablets of 200 mcg): 4 tablets under the tongue for 30 minutes, every 3 hours,
  3 times. Swallow what remains after 30 minutes each time.
- Do not eat or drink during the 30 minutes the pills dissolve. Eating and drinking before and after is fine.
- Normal effects: cramps, chills, mild fever, nausea, diarrhea. Bleeding usually starts 2 to 4 hours after
  misoprostol; heaviest bleeding lasts 1 to 4 hours with clots, then eases.
- Pain relief: ibuprofen 400 to 600 mg; 600 mg can be taken after the first misoprostol dose.
- MVA (manual vacuum aspiration) is a short procedure done in a clinic. A counselor can share clinic information.
- Women with health problems can still use the pills; they should have someone with them and be near medical care.
- Plan: someone for emotional support, childcare arranged, a calm private place with a bathroom, painkillers
  ready, and know where to go if extra care is needed. Where to get pills: a counselor discusses this privately.

4 warning signs that need medical care now:
1. Soaking more than 2 maxi pads per hour for 2 to 3 hours in a row, or bleeding like an open tap.
2. Severe pain that painkillers do not relieve.
3. Bad-smelling vaginal discharge.
4. Fever over 38 C for more than 24 hours, or over 39 C at any time.
Complications are treated exactly like a miscarriage; a woman can go to any clinic and say she had a miscarriage.

After: bleeding decreases gradually and can last 1 to 3 weeks; period returns in 4 to 6 weeks. Nothing in the
vagina (no sex, tampons, baths) for 2 to 3 days. Pregnancy test after 3 to 4 weeks (earlier can be falsely
positive). Pregnancy is possible again immediately.
Contraception: pill, patch, injection, implant can start up to 5 days after misoprostol and protect immediately;
vaginal ring after 2 to 3 days; IUD once complete abortion is confirmed or at the next period; condoms as soon as
sex resumes; fertility awareness once cycles are regular.
"""

SYSTEM_PROMPT = """You help the Aunty Queen Hotline WhatsApp assistant. A client is answering intake questions.
You get the CURRENT QUESTION the bot asked, its allowed OPTIONS (if any), and the CLIENT MESSAGE.

Return only JSON: {"kind": ..., "option_id": ..., "value": ..., "reply": ...}
kind is one of:
- "answer": the message answers the current question. Set option_id to the matching option id if there are
  options, and value to the answer in a few words.
- "question": the client asks something else. Put a short, kind answer in reply.
- "urgent": the client describes a warning sign happening now (heavy bleeding, severe pain, bad-smelling
  discharge, high fever) or any emergency. reply: tell her to go to the nearest health facility now and that it
  is treated like a miscarriage.
- "human": the client asks to talk to a person, is distressed, or the topic is outside the knowledge below.
  reply: say a counselor will reply here.
- "unclear": none of the above. reply: empty.

Rules for reply: use ONLY the knowledge below, never invent doses, places, prices or medical advice beyond it.
Write in LANGUAGE. Plain WhatsApp text, at most 600 characters, warm and non-judgmental. Never ask for her
full name, address or ID. Do not repeat the current question; the bot does that.

KNOWLEDGE:
""" + KNOWLEDGE


def classify(current_question, options, message, language="en"):
    """Returns a dict like {"kind", "option_id", "value", "reply"}, or None if AI is off or fails."""
    if not AI_API_KEY:
        return None
    opts = "\n".join(f"- {oid}: {title}" for oid, title in options) if options else "(free text answer)"
    user = (
        f"LANGUAGE: {'French' if language == 'fr' else 'English'}\n"
        f"CURRENT QUESTION: {current_question}\nOPTIONS:\n{opts}\nCLIENT MESSAGE: {message[:1000]}"
    )
    try:
        r = requests.post(
            f"{AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": AI_MODEL,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT.replace("LANGUAGE", "the client's language")},
                    {"role": "user", "content": user},
                ],
            },
            timeout=20,
        )
        r.raise_for_status()
        result = json.loads(r.json()["choices"][0]["message"]["content"])
        if result.get("kind") not in ("answer", "question", "urgent", "human", "unclear"):
            return None
        valid_ids = {oid for oid, _ in options or []}
        if result.get("option_id") not in valid_ids:
            result["option_id"] = None
        result["reply"] = (result.get("reply") or "")[:900]
        return result
    except Exception as e:
        print(f"[AI error]: {e}")
        return None
