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

## Deploy

- **Frontend:** e.g. Vercel (static) — set `BACKEND_URL` to your backend URL.
- **Backend:** e.g. Railway — set `FETCHTRANSCRIPT_API_KEY`, `ANTHROPIC_API_KEY`, and (for voice-over) `AI33_API_KEY`, `AI33_BASE_URL`, `AI33_VOICE_ID`, `AI33_MODEL` in the project environment.
