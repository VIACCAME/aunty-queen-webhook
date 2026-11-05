"""Free-text helper: answers side questions during the intake, then the bot re-asks the current question.

Uses any OpenAI-compatible chat API. Default is Groq's free tier.
For Gemini: AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai and AI_MODEL=gemini-3.5-flash.
Only the client's message and the current question are sent. No phone number or name.
"""
import json
import os
import time

import requests

AI_API_KEY = os.environ.get("AI_API_KEY")
AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
AI_MODEL = os.environ.get("AI_MODEL", "llama-3.3-70b-versatile")
# Tried in order when the main model is busy (429/503) or slow. Defaults suit Gemini's free tier.
_default_fallback = "gemini-3.5-flash-lite,gemini-flash-lite-latest" if "googleapis" in AI_BASE_URL else ""
AI_FALLBACK_MODELS = [m.strip() for m in os.environ.get("AI_FALLBACK_MODELS", _default_fallback).split(",") if m.strip()]


def chat(messages, json_mode=False, timeout=20):
    """One chat completion, retrying busy errors and falling back to lighter models. Returns text or None."""
    models = [AI_MODEL] + [m for m in AI_FALLBACK_MODELS if m != AI_MODEL]
    attempts = [models[0], models[0]] + models[1:]
    for i, model in enumerate(attempts):
        body = {"model": model, "temperature": 0.2, "messages": messages}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            r = requests.post(f"{AI_BASE_URL}/chat/completions", json=body, timeout=timeout,
                              headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"})
            if r.status_code in (429, 500, 502, 503, 504):
                print(f"[AI busy] {model}: {r.status_code}")
                time.sleep(0.6 if i == 0 else 0.2)
                continue
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[AI error] {model}: {e}")
    return None

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
- "question": the client asks something (how, what, why, when, can, will, is it…), even if it is about the
  same topic as the current question or comes before agreeing to it. A message that asks something is ALWAYS
  "question", never "answer". Put a short, kind answer in reply.
- "urgent": the client describes a warning sign happening now (heavy bleeding, severe pain, bad-smelling
  discharge, high fever) or any emergency. reply: tell her to go to the nearest health facility now and that it
  is treated like a miscarriage.
- "human": the client asks to talk to a person, is distressed, or the topic is outside the knowledge below.
  reply: say a counselor will reply here.
- "unclear": none of the above. reply: empty.

Rules for reply: use ONLY the knowledge below, never invent doses, places, prices or medical advice beyond it.
Write in the LANGUAGE given in the message. Sound like a caring, trusted aunty: warm, calm, simple words, short
sentences, never judgmental. You may call her "my dear" in English or "ma chérie" in French (use "tu" in French).
Plain WhatsApp text, *bold* allowed, at most one emoji, at most 600 characters. Never ask for her full name,
address or ID. Do not repeat the current question; the bot does that.

KNOWLEDGE:
""" + KNOWLEDGE


SUMMARY_PROMPT = """You write short case notes for counselors at the Aunty Queen Hotline (Cameroon).
You get one client's intake answers as JSON. Write 2 to 4 short lines in English for the counselor:
who she is (age, town, gender if not a woman), what she needs, her situation (weeks / last period, method or
preference, health issues, support), anything urgent, and the next action for the counselor
(for example: prepare a misoprostol-only pack, prepare mifepristone + misoprostol, refer for MVA, call back
at the agreed time, check warning signs). Facts only from the JSON, no invented details, no judgement.
Plain text, no markdown, at most 400 characters."""


def summarize(data, status=""):
    """A short counselor note for one intake, or "" if AI is off or fails."""
    if not AI_API_KEY:
        return ""
    # No name or phone is sent to the AI.
    fields = {k: v for k, v in (data or {}).items() if v not in ("", None) and k not in ("consent", "name")}
    fields["status"] = status
    text = chat([{"role": "system", "content": SUMMARY_PROMPT},
                 {"role": "user", "content": json.dumps(fields, ensure_ascii=False)[:3000]}], timeout=30)
    return (text or "").strip()[:500]


def classify(current_question, options, message, language="en"):
    """Returns a dict like {"kind", "option_id", "value", "reply"}, or None if AI is off or fails."""
    if not AI_API_KEY:
        return None
    opts = "\n".join(f"- {oid}: {title}" for oid, title in options) if options else "(free text answer)"
    user = (
        f"LANGUAGE: {'French' if language == 'fr' else 'English'}\n"
        f"CURRENT QUESTION: {current_question}\nOPTIONS:\n{opts}\nCLIENT MESSAGE: {message[:1000]}"
    )
    text = chat([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}], json_mode=True)
    if not text:
        return None
    try:
        result = json.loads(text.strip().removeprefix("```json").removesuffix("```").strip())
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
