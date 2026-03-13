# Sentence Match Workflow

One input: YouTube video URL. Output: sentence match (EN/DE), TTS text, translated title, and credits — all with copy buttons.

## Setup

### Backend

1. **Create a virtualenv and install dependencies**
   ```bash
   cd backend
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Environment variables**
   Copy `backend/.env.example` to `backend/.env` and set:
   - `FETCHTRANSCRIPT_API_KEY` — your [FetchTranscript.com](https://fetchtranscript.com) API key (starts with `yt_`)
   - `ANTHROPIC_API_KEY` — your Anthropic (Claude) API key
   - **Voice-over (optional):** `AI33_API_KEY`, `AI33_BASE_URL` (from ai33 API docs), `AI33_VOICE_ID` (default: Lars), `AI33_MODEL` (e.g. `eleven_multilingual_v3`)

3. **Run the backend**
   ```bash
   cd backend
   source .venv/bin/activate
   uvicorn app.main:app --reload --port 8001
   ```

### Frontend

Open `index.html` in a browser, or serve it (e.g. with Vercel or any static host). Set `BACKEND_URL` in `index.html` to your backend (e.g. `http://localhost:8001` for local, or your Railway URL in production).

## Usage

1. Paste a YouTube URL (or 11-character video ID) into the input.
2. Click **Process**. Title, sentence match, TTS text, and credits appear; the voice-over is generated automatically and shown in its own card.
3. In the Voice-over card: use **Play** and the seek bar to listen; click **Download** to save the MP3 (no automatic download). TTS text is shown with copy; for playback the backend strips `[speak fast]` and similar bracket instructions so they are not spoken.

## Project layout

- `index.html` — frontend (single page)
- `backend/app/` — FastAPI app
  - `api/process.py` — `POST /api/process` (video_url → results)
  - `api/voiceover.py` — `POST /api/voiceover` (tts_text → MP3 download)
  - `services/transcript.py` — FetchTranscript API client
  - `services/voiceover.py` — ai33 TTS (ElevenLabs v3, voice Lars)
  - `services/translate.py` — Claude translation + response parsing
  - `utils/video.py` — YouTube video ID extraction
  - `utils/credits.py` — credits from description
  - `prompts/` — system prompt and German style examples (edit these to tune output)

### Optional: Trello + Drive + Sources sheet

- **Trello:** Set `TRELLO_API_KEY`, `TRELLO_TOKEN`, `TRELLO_BOARD_ID`, `TRELLO_TEMPLATE_CARD_ID` to enable "Create Trello card".
- **Drive:** Set `GOOGLE_SERVICE_ACCOUNT_JSON` (or `GOOGLE_SERVICE_ACCOUNT_FILE`) and `DRIVE_ROOT_FOLDER_ID` for folder creation and voice-over upload. Same Google Cloud project as below.
- **Sources sheet (source IDs on cards):** No extra API keys. Use the **same Google service account** as Drive. Enable the **Google Sheets API** in your [Google Cloud Console](https://console.cloud.google.com/apis/library/sheets.googleapis.com) for that project. Then:
  1. Create a new Google Sheet (or use an existing one).
  2. Share the sheet with the **service account email** (from your JSON key, field `client_email`) with **Editor** permission.
  3. Set `SOURCES_SHEET_ID` to the sheet ID from the URL: `https://docs.google.com/spreadsheets/d/<SOURCES_SHEET_ID>/edit`.  
  When creating a Trello card, the backend will look up or create a row keyed by video URL and put the ID on the card as `[ SRC0001 ]` (and so on). Optional: set `SOURCES_SHEET_TAB` if your tab is not the default (e.g. `Sheet1`).

## Deploy

- **Frontend:** e.g. Vercel (static) — set `BACKEND_URL` to your backend URL.
- **Backend:** e.g. Railway — set `FETCHTRANSCRIPT_API_KEY`, `ANTHROPIC_API_KEY`, and (for voice-over) `AI33_API_KEY`, `AI33_BASE_URL`, `AI33_VOICE_ID`, `AI33_MODEL` in the project environment.
