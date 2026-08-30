# DispatchProof V2.46 Render Deploy

Deploy normally over V2.45.2. The migration is automatic and additive; do not reset the database.

## Existing Render storage
Keep the current persistent storage setting unchanged:

`DISPATCHPROOF_DATA_DIR=/var/data/dispatchproof`

Subcontractor documents and voice recordings are stored in the normal DispatchProof uploads directory and therefore use the same persistent disk.

## Optional automatic voice transcription
Voice recording/audio storage works without any new environment variable. To enable automatic transcription, add either:

`OPENAI_API_KEY=<your API key>`

or:

`DISPATCHPROOF_OPENAI_API_KEY=<your API key>`

Optional model override:

`DISPATCHPROOF_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe`

Do not commit API keys to GitHub. Add them directly in Render Environment settings. Saving an environment variable may trigger a redeploy.

## Existing provider keys
Do not change the existing Foursquare or openrouteservice/HeiGIT keys. V2.46 does not alter those integrations.

## First QA after deploy
1. Confirm footer/version shows 2.46.0.
2. Test one subcontractor document with an expiration inside its warning window.
3. Test Snow Plowing / Snow Removal search.
4. Create one Field Access link with a selected document.
5. Open it from a phone and record a short voice update.
6. Confirm audio reaches the PM; if transcription is configured, confirm the transcript appears too.
