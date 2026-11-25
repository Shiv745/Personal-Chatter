"""Gemini AI Brain: Custom Style & Target Steering, Sharp Humour, Romantic Charm, LinkedIn Personas, Vision & Auto-Memory."""
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from google import genai
from google.genai import types

import config_manager
import database as db


def _extract_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return {}


class ChatBrain:
    def __init__(self) -> None:
        self.client: Optional[genai.Client] = None
        self.cfg: Dict[str, Any] = {}
        self.reload_client()

    def reload_client(self) -> bool:
        self.cfg = config_manager.load_config()
        api_key = (self.cfg.get("gemini_api_key") or "").strip()
        base_url = (self.cfg.get("custom_base_url") or "").strip()

        if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
            self.client = None
            return False

        try:
            if base_url:
                self.client = genai.Client(
                    api_key=api_key,
                    http_options=types.HttpOptions(base_url=base_url),
                )
            else:
                self.client = genai.Client(api_key=api_key)
            return True
        except Exception as e:
            db.log_event("system", f"Gemini client init error: {e}", level="error")
            self.client = None
            return False

    def is_connected(self) -> bool:
        return self.client is not None

    @property
    def primary_model(self) -> str:
        return self.cfg.get("primary_model") or "gemini-3.5-flash"

    @property
    def propose_model(self) -> str:
        return self.cfg.get("propose_model") or "gemini-3.5-flash"

    @property
    def fallback_model(self) -> str:
        return self.cfg.get("fallback_model") or "gemini-3.5-flash"

    def _generate_content(self, model: str, contents: Any, config: Any) -> Any:
        """Generate content, falling back when the selected model is capacity-limited."""
        try:
            return self.client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            error_text = str(exc).upper()
            capacity_limited = any(marker in error_text for marker in (
                "429",
                "503",
                "UNAVAILABLE",
                "RESOURCE_EXHAUSTED",
                "HIGH DEMAND",
            ))
            fallback = self.fallback_model.strip()
            if capacity_limited and fallback and fallback != model:
                db.log_event(
                    "system",
                    f"Gemini model {model} is unavailable; falling back to {fallback}.",
                    level="warn",
                )
                return self.client.models.generate_content(
                    model=fallback,
                    contents=contents,
                    config=config,
                )
            raise

    @property
    def user_name(self) -> str:
        return self.cfg.get("your_name") or "Shivendra"

    def _build_system_prompt(
        self,
        ctx: Dict[str, Any],
        force_propose: bool = False,
        target_override: str = "",
    ) -> str:
        c = ctx["contact"]
        p = ctx["profile_intel"]
        platform = c["platform"]
        persona = c.get("persona") or ("professional" if platform == "linkedin" else "personal")
        facts_text = "\n".join(
            [f"- [{f['category']}] {f['fact']}" for f in ctx["memory_facts"]]
        ) or "None saved yet."

        custom_style = (c.get("chat_style") or "").strip()
        active_target = (target_override or c.get("chat_target") or "").strip()

        custom_block_parts = []
        if custom_style:
            custom_block_parts.append(
                f"- USER'S CUSTOM CHAT STYLE (HIGHEST PRIORITY): {custom_style}\n"
                "  Strictly match this exact tone, vibe, and texting instruction."
            )
        if active_target:
            if force_propose:
                custom_block_parts.append(
                    f"- EXECUTE TARGET RIGHT NOW: {active_target}\n"
                    "  Make the move smoothly, naturally, confidently, and memorably in this exact reply! "
                    "Use her/their vibe, favourite songs, or inside jokes if it fits naturally."
                )
            else:
                custom_block_parts.append(
                    f"- CONVERSATION TARGET / GOAL: {active_target}\n"
                    "  Subtly and smoothly steer the chat toward this target over the next few messages. "
                    "Build comfort and chemistry first — if the opening is natural right now, go for it; otherwise set up the perfect opening without sounding pushy."
                )
        custom_directives = "\n".join(custom_block_parts) if custom_block_parts else "No custom override — use default natural flow."

        # --- LINKEDIN PROFESSIONAL PERSONA ---
        if persona == "professional":
            default_action = (
                f"SPECIAL ACTION: Smoothly execute this goal right now -> '{active_target or 'Propose a quick intro call or next step'}'."
                if force_propose
                else "Focus on building genuine rapport, clear communication, and moving smoothly toward the conversation goal."
            )
            return f"""
You are messaging AS {self.user_name} on {platform.title()} with {c['name']} ({c['handle']}).
You are a sharp, confident, warm Cloud & DevOps / Tech professional — NEVER robotic, NEVER generic corporate fluff.

USER-DEFINED STYLE & TARGET DIRECTIVES:
{custom_directives}

COMMUNICATION STYLE (PROFESSIONAL):
1. Crisp, confident, human English (match their formality; friendly yet polished).
2. Zero clichés like "I hope this message finds you well" or "synergy".
3. Keep messages concise (1 to 2 short bubbles/paragraphs).
4. Reference their role, company, or recent posts ONLY naturally if genuinely relevant.
5. {default_action}

THEIR LINKEDIN INTEL:
- Role & Company: {p.get('role_company', '')}
- Bio/About: {p.get('bio_summary', '')}
- Top Skills: {p.get('skills', '')}
- Recent Activity/Topics: {p.get('recent_activity', '')}
- Conversation Goal: {p.get('conversation_goal', '')}

SAVED MEMORY NOTES:
{facts_text}
""".strip()

        # --- FRIENDLY / CASUAL NETWORKING PERSONA ---
        if persona == "friendly":
            return f"""
You are texting AS {self.user_name} on {platform.title()} with {c['name']} ({c['handle']}).
Vibe: Chill, witty, warm, approachable friend — good sense of humour, zero awkward pressure.
Match their language (English or Hinglish). Send 1 to 2 short natural bubbles.

USER-DEFINED STYLE & TARGET DIRECTIVES:
{custom_directives}

INTEL:
- Bio: {p.get('bio_summary', '')}
- Role/Hobbies: {p.get('role_company', '')} {p.get('hobbies', '')}
- Likes: {p.get('likes', '')}
- Fav Songs: {p.get('fav_songs', '')}

MEMORY FACTS:
{facts_text}
""".strip()

        # --- PERSONAL / ROMANTIC + SHARP HUMOUR PERSONA (Default for Insta & WhatsApp) ---
        if force_propose:
            goal_label = active_target or "Confess your feelings / propose warmly"
            propose_rule = (
                f"SPECIAL TRIGGER ACTIVE: Execute this exact move right now -> '{goal_label}'. "
                "Make it genuinely memorable, warm, charming, and confident. Weave in her vibe, favourite songs, or an inside joke if it fits naturally. "
                "Heartfelt + slightly playful — ZERO filmy melodrama or cheesy shayari."
            )
        else:
            propose_rule = (
                f"Active Target to steer toward smoothly: '{active_target}'."
                if active_target
                else "Do NOT suddenly propose unless stage is already 'romantic', warmth_score >= 8, and she is actively reciprocating romantic vibes."
            )

        return f"""
You are texting AS {self.user_name} on {platform.title()} to {c['name']} (@{c['handle']}).
You are a real, charming, grounded Indian guy — NOT an AI assistant.

USER-DEFINED STYLE & TARGET DIRECTIVES (FOLLOW CLOSELY):
{custom_directives}

PERSONALITY & CHAT STYLE (CRITICAL — THIS MUST IMPRESS HER):
1. Razor-Sharp Sense of Humour: Quick-witted, playful teasing, light banter, clever callbacks, and subtle sarcasm that makes her genuinely smile or laugh. Strictly NO dad jokes, NO Santa-Banta jokes, NO cheesy pickup lines, NO cringe shayari.
2. Confident & Effortless: Zero desperation, zero simping, never over-explain. Keep texts crisp and natural like real Instagram/WhatsApp chatting.
3. Natural Language Mirroring: Match her exact language mix — casual English, Hinglish (Hindi in Roman script), or pure Hindi in Roman script. Never sound translated or stiff.
4. Multi-Bubble Pacing: Real people send 1 to 3 short texts instead of one wall of text. Split thoughts naturally into short bubbles. Use emojis sparingly (0 to 1 max per reply, only when it elevates the vibe).
5. Anti-Stalker Rule: You know her profile intel (songs, hobbies, likes) below. NEVER bluntly say "I saw your old post" or act creepy. Drop subtle, natural references only when the moment fits.
6. Emotional Intelligence: If she sounds upset, stressed, tired, or serious, immediately drop the teasing and be genuinely caring, warm, and attentive.

RELATIONSHIP STATE:
- Current Stage: {c['stage']} (progression: casual -> flirty -> romantic -> propose)
- Warmth Score: {c['warmth_score']}/10
- {propose_rule}

HER PROFILE INTEL (Saved in SQLite):
- Bio Summary: {p.get('bio_summary', '')}
- Favourite Songs / Music: {p.get('fav_songs', '')}
- Hobbies: {p.get('hobbies', '')}
- Likes: {p.get('likes', '')}
- Dislikes: {p.get('dislikes', '')}
- Vibe Notes: {p.get('vibe_notes', '')}

SAVED MEMORY FACTS & INSIDE JOKES:
{facts_text}
""".strip()

    def _format_history(self, recent_messages: List[Dict[str, Any]]) -> str:
        if not recent_messages:
            return "(Start of conversation)"
        lines = []
        for m in recent_messages:
            who = self.user_name if m["sender"] == "me" else "Them"
            lines.append(f"{who}: {m['content']}")
        return "\n".join(lines)

    def generate_reply(
        self,
        contact_id: int,
        incoming_text: str,
        mode: str = "autopilot",
        force_propose: bool = False,
        target_override: str = "",
    ) -> Dict[str, Any]:
        if not self.client and not self.reload_client():
            raise RuntimeError("Gemini API Key is not configured. Open Settings tab and add your API key.")

        ctx = db.get_full_context(contact_id)
        if not ctx:
            raise ValueError(f"Contact ID {contact_id} not found")

        sys_prompt = self._build_system_prompt(
            ctx, force_propose=force_propose, target_override=target_override
        )
        history_str = self._format_history(ctx["recent_messages"])
        model_name = self.propose_model if force_propose else self.primary_model
        persona = ctx["contact"].get("persona", "personal")

        if mode == "copilot":
            if persona == "professional":
                schema_hint = """{
  "opt1_label": "Professional",
  "opt1": ["short natural message 1"],
  "opt2_label": "Polite & Warm",
  "opt2": ["short natural message 1"],
  "opt3_label": "Target-Focused",
  "opt3": ["short natural message moving toward the set target"],
  "mood_detected": "professional|warm|neutral|interested|busy"
}"""
            else:
                schema_hint = """{
  "opt1_label": "Funny",
  "opt1": ["short witty bubble 1", "optional bubble 2"],
  "opt2_label": "Romantic / Target",
  "opt2": ["short charming bubble 1 steering toward target", "optional bubble 2"],
  "opt3_label": "Casual",
  "opt3": ["short chill bubble 1"],
  "mood_detected": "playful|warm|neutral|serious|upset|flirty"
}"""
            user_prompt = f"""
Recent conversation:
{history_str}

Latest incoming message: "{incoming_text}"

Return strict JSON with 3 distinct reply options:
{schema_hint}
"""
        else:
            user_prompt = f"""
Recent conversation:
{history_str}

Latest incoming message: "{incoming_text}"

Reply as {self.user_name} in strict JSON format:
{{
  "bubbles": ["short text 1", "optional short text 2"],
  "mood_detected": "playful|warm|neutral|serious|upset|flirty|professional",
  "needs_approval": false,
  "approval_reason": "",
  "suggested_stage": "casual|flirty|romantic|propose",
  "warmth_delta": 0
}}

Rules:
- Set needs_approval=true ONLY if their message is deeply emotional/upset, asks to meet/call right now, involves a job offer/salary/sensitive topic, or you are executing a major proposal/I-love-you confession.
- warmth_delta must be -1, 0, or 1.
- Keep each bubble crisp and natural (no walls of text).
"""

        resp = self._generate_content(
            model=model_name,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=sys_prompt,
                temperature=0.82 if persona != "professional" else 0.55,
                response_mime_type="application/json",
            ),
        )

        data = _extract_json(resp.text or "")
        if not data:
            fallback = (resp.text or "Hey!").strip()
            if mode == "copilot":
                return {
                    "opt1_label": "Option 1", "opt1": [fallback],
                    "opt2_label": "Option 2", "opt2": [fallback],
                    "opt3_label": "Option 3", "opt3": [fallback],
                    "mood_detected": "neutral",
                }
            return {
                "bubbles": [fallback],
                "mood_detected": "neutral",
                "needs_approval": False,
                "approval_reason": "",
                "suggested_stage": ctx["contact"]["stage"],
                "warmth_delta": 0,
            }
        return data

    def extract_and_save_memories(self, contact_id: int) -> bool:
        """Silently inspects recent messages and updates SQLite with songs, likes, inside jokes, events."""
        if not self.client and not self.reload_client():
            return False

        ctx = db.get_full_context(contact_id)
        if not ctx or not ctx["recent_messages"]:
            return False

        recent = ctx["recent_messages"][-8:]
        history_str = self._format_history(recent)
        prompt = f"""
Analyze this recent chat snippet and extract ONLY concrete new facts about the OTHER person (NOT {self.user_name}).
Return strict JSON:
{{
  "fav_songs": "comma separated songs/artists if mentioned, else empty string",
  "hobbies": "comma separated hobbies if mentioned, else empty string",
  "likes": "comma separated likes if mentioned, else empty string",
  "dislikes": "comma separated dislikes if mentioned, else empty string",
  "role_company": "role/company if mentioned, else empty string",
  "skills": "comma separated skills if mentioned, else empty string",
  "facts": [
    {{"category": "song|like|dislike|event|inside_joke|personal|career", "fact": "short clear note"}}
  ]
}}

Chat:
{history_str}
"""
        try:
            resp = self._generate_content(
                model=self.primary_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
            )
            extracted = _extract_json(resp.text or "")
            if not extracted:
                return False

            old = ctx["profile_intel"]

            def merge_csv(old_val: str, new_val: str) -> str:
                items = [x.strip() for x in (old_val or "").split(",") if x.strip()]
                for n in (new_val or "").split(","):
                    n = n.strip()
                    if n and n.lower() not in [i.lower() for i in items]:
                        items.append(n)
                return ", ".join(items)

            db.save_profile_intel(
                contact_id=contact_id,
                fav_songs=merge_csv(old.get("fav_songs", ""), extracted.get("fav_songs", "")),
                hobbies=merge_csv(old.get("hobbies", ""), extracted.get("hobbies", "")),
                likes=merge_csv(old.get("likes", ""), extracted.get("likes", "")),
                dislikes=merge_csv(old.get("dislikes", ""), extracted.get("dislikes", "")),
                role_company=extracted.get("role_company", "") or old.get("role_company", ""),
                skills=merge_csv(old.get("skills", ""), extracted.get("skills", "")),
            )

            for item in extracted.get("facts", []):
                db.add_memory_fact(
                    contact_id,
                    item.get("category", "personal"),
                    item.get("fact", ""),
                )
            return True
        except Exception as e:
            db.log_event("system", f"Memory extraction error: {e}", level="warn")
            return False

    def analyze_instagram_profile(
        self,
        raw_text: str,
        audio_tags: List[str],
        screenshot_path: Optional[Path] = None,
    ) -> Dict[str, str]:
        if not self.client and not self.reload_client():
            raise RuntimeError("Gemini API Key missing.")

        prompt = f"""
You are analyzing an Instagram profile to build a clean, structured personal memory card.
Combine the scraped text, detected reel/post audio tags, and the attached screenshot (if any).
Return strict JSON:
{{
  "bio_summary": "concise 1-2 line summary of who they are",
  "fav_songs": "comma separated songs, artists, or music genres noticed from bio/reels/audio",
  "hobbies": "comma separated hobbies/interests",
  "likes": "comma separated likes (food, travel, aesthetics, pets, etc.)",
  "dislikes": "comma separated dislikes if evident, else empty string",
  "vibe_notes": "short note on their personality vibe and good casual conversation starters"
}}

Scraped Text:
{raw_text[:5000]}

Detected Audio/Music Labels:
{", ".join(audio_tags) if audio_tags else "None detected"}
"""
        contents: List[Any] = [prompt]
        if screenshot_path and screenshot_path.exists():
            img_bytes = screenshot_path.read_bytes()
            contents.append(
                types.Part.from_bytes(data=img_bytes, mime_type="image/png")
            )

        resp = self._generate_content(
            model=self.primary_model,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json",
            ),
        )
        return _extract_json(resp.text or "")

    def analyze_linkedin_profile(self, raw_text: str) -> Dict[str, str]:
        if not self.client and not self.reload_client():
            raise RuntimeError("Gemini API Key missing.")

        prompt = f"""
Analyze this LinkedIn profile text and return strict JSON:
{{
  "role_company": "Current Role @ Company",
  "bio_summary": "1-2 line crisp summary of background & focus",
  "skills": "comma separated top 5-8 skills",
  "recent_activity": "comma separated topics they post/engage about",
  "conversation_goal": "best natural networking angle"
}}

Profile Text:
{raw_text[:6500]}
"""
        resp = self._generate_content(
            model=self.primary_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.25,
                response_mime_type="application/json",
            ),
        )
        return _extract_json(resp.text or "")
