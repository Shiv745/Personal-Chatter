# PulseAI Agent — Windows Desktop AI Chat Agent
*(Instagram + WhatsApp + LinkedIn | Gemini API | SQLite Memory | Human-like Playwright Automation)*

## Features
- **Custom Chat Style & Target Steering (NEW in v2.0):** Type exactly *how* you want the agent to chat (e.g., playful teasing, soft romantic, witty Hinglish) and set a specific *Target* per contact (e.g., `Coffee Date`, `Propose for Date`, `Say I Love You`, `Schedule Call`), plus 1-click quick-target chips and an **Execute Target Now** trigger.
- **3 Platforms Concurrently:** Monitors **Instagram**, **WhatsApp Web**, and **LinkedIn Messaging** in parallel using a single persistent Chrome/Chromium profile with an async typing lock (types in one tab at a time like a real human).
- **3 Control Modes:**
  - **Full Autopilot (Default):** Reads, pauses naturally, types character-by-character with occasional self-corrected typos, splits long replies into short bubbles, and sends.
  - **Hybrid Mode:** Handles normal banter automatically; pauses for your approval on emotional/sensitive messages, meeting requests, or proposals.
  - **Co-pilot Mode:** Gives 3 one-click reply chips (`Funny`, `Romantic`, `Casual` — or `Professional`, `Polite`, `Brief` on LinkedIn).
- **Sharp Humour & Natural Charm:** Built for witty Hinglish/English banter, playful teasing, clever callbacks, and personalized proposals — zero cringe shayari.
- **Instagram Profile + Song Scanner (Gemini Vision):** Slowly scans bio, recent posts, and reel audio tags once and saves favourite songs, hobbies, and likes into SQLite (`agent_memory.db`).
- **LinkedIn Profile Scanner & Persona Switcher:** Scans role, company, skills, and recent topics; switch per-contact between `Professional`, `Friendly`, and `Personal`.
- **Anti-Ban Protection:** Randomized polling intervals, reading delays, human typing speed, rolling hourly reply caps, strict whitelist, and automatic pause on CAPTCHA/security screens.
- **Editable Gemini Model & Base URL:** Uses `gemini-3.5-flash` by default with automatic fallback support, or any custom model IDs / proxy gateway via the **Settings** tab.

---

## Quick Setup in VS Code (Windows)

1. **Extract** `PulseAI_Chat_Agent.zip` and open the `PulseAI_Chat_Agent` folder in **VS Code**.
2. **Install Dependencies (1-Click):**
   - Double-click `setup.bat` (or run `.\setup.bat` in VS Code terminal).
   - This creates `.venv`, installs all Python packages, and installs Playwright Chromium.
3. **Add Your Gemini API Key:**
   - Open `config.json` and paste your Gemini API key into `"gemini_api_key"` (or paste it inside the App's **Settings** tab after launching).
   - You can also edit `primary_model`, `propose_model`, or `custom_base_url` anytime in **Settings**.
4. **Launch the Windows Desktop App:**
   - Press **F5** in VS Code (`.vscode/launch.json` is pre-configured), OR double-click `run.bat`.
   - *(Optional: Run `python main.py --web` if you prefer viewing the dashboard in your normal browser.)*

---

## First-Time Usage Flow

1. **Test the AI Vibe First (No Browser Needed):**
   - Pick a Demo contact on the Instagram, WhatsApp, or LinkedIn tab.
   - Keep the composer dropdown on **Simulate Incoming (Test AI)** and send a test message to see how witty, romantic, or professional Gemini replies.
2. **Whitelist Real Contacts:**
   - Click **+ Add Contact** and add the exact Instagram username, WhatsApp contact name, or LinkedIn full name/URL.
   - Only whitelisted contacts receive automated replies.
3. **Start Live Browser Automation:**
   - Click **▶ Start** in the top-right bar.
   - A Chrome window opens with 3 tabs (WhatsApp Web, Instagram, LinkedIn). Scan QR / log in **once** — your session is saved in `browser_profile/`.
4. **Scan Profile & Songs:**
   - Click **⟳ Scan Profile** in the right sidebar on Instagram or LinkedIn to auto-populate Bio, Favourite Songs, Hobbies/Skills, and Vibe Notes into `agent_memory.db`.
