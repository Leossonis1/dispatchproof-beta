
# DispatchProof V1.5 — Render Beta

This is the first public-deployment build of DispatchProof.

Start locally:

```bat
python -m pip install -r requirements.txt
python app.py
```

Deploy to Render using the included:

- `render.yaml`
- `DEPLOY_RENDER.md`

## Important

The included Render Blueprint uses the **Free** web-service plan for the first
public workflow test. Free Render filesystem storage is temporary, so this is
not yet the durable production configuration.

When we want persistent beta data, V1.5 already supports:

`DISPATCHPROOF_DATA_DIR=/var/data/dispatchproof`

with a Render persistent disk.

## V1.5 features retained

- readiness workflow
- dispatch gating
- photo proof
- failed-mobilization reports
- immutable mobilization history
- multi-attempt jobs
- email preview/outbox
- SMTP email support
- reminder workflow
