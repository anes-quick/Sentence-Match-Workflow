# Idea: Optional Trello (+ Drive) Module

**Status:** Brainstorm / future work. Not implemented yet.

---

## Goal

The Sentence Match Workflow tool is used to get information from a YouTube video (script, sentence match, title, credits, voice-over). A VA then copies that info and creates a Trello card manually.

**Idea:** Add an optional module that creates a **"Create Trello card"** button. When clicked, it takes all current tool data, fills a Trello card from a template (and optionally creates a Drive folder for the voice-over), so the VA only has to double-check and push the button.

---

## Requirements

- **Modular:** The Trello/Drive logic must be clearly split from the rest of the app so it can be **turned off** (e.g. via config / env) when not needed.
- **Button:** Placed at the bottom of the current tool: **"Create Trello card"**.
- **Data used:** All current result data: translated title, sentence match, TTS text, credits, and voice-over (file or link).
- **Trello:** Create a card (e.g. from an existing template card or a fixed structure) and fill it with the above data.
- **Drive (optional):** Create a folder for the voice-over, upload the MP3, get a shareable link, and add that link to the Trello card so the VA has everything in one place.

---

## How to Keep It Separate

- **Frontend:** Show the "Create Trello card" button (and any Trello-related UI) only when the feature is enabled (e.g. config or env like `TRELLO_MODULE_ENABLED`).
- **Backend:** Put all Trello (and optional Drive) logic in its own module (e.g. `services/trello.py`, `api/trello.py`). Register those routes only if the right env vars are set (e.g. `TRELLO_API_KEY`, `TRELLO_BOARD_ID`). No config = no Trello code runs.
- **Core tool:** The existing flow (YouTube → transcript, sentence match, title, credits, voice-over) stays unchanged. The Trello part is an add-on that can be disabled.

---

## Technical Notes

- **Trello API:** Can create cards, copy from a template card, set title/description, custom fields, and attachments. Template can be implemented by copying an existing "template" card or by defining list id, labels, and description template in code.
- **Google Drive API:** Can create a folder, upload the voice-over MP3, and return a shareable link to add to the Trello card.
- **Auth:** Trello uses API key + token (or OAuth). Drive uses a service account or OAuth; tokens must be stored and used securely.
- **Voice-over:** Either upload MP3 to Drive and put the link on the card, or attach the file to the Trello card via API (subject to size limits). Drive folder + link is usually more flexible.

---

## Possible Next Steps (when implementing later)

1. Define env vars and feature flag (e.g. `TRELLO_MODULE_ENABLED`, `TRELLO_API_KEY`, `TRELLO_BOARD_ID`, optional Drive credentials).
2. Add backend module: `services/trello.py` (and optionally `services/drive.py`), `api/trello.py`, only loaded when config is present.
3. Add one or two endpoints, e.g. `POST /api/trello/create-card` with body: title, sentence_match, tts_text, credits, voice_over_base64_or_url.
4. Add "Create Trello card" button at the bottom of the frontend, visible only when the Trello module is enabled; button sends current result data to the new endpoint.
5. Implement Trello card creation from template (copy template card or create from structure) and optional Drive folder + upload + link on card.

---

*Document created for future reference. Revisit after stress testing the current tool.*
