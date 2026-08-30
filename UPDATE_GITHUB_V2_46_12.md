# DispatchProof V2.46.12 — Launch & Operations Baseline

## Files changed
- `app.py`
- `render.yaml`
- `VERSION.txt`
- `README.md`
- `DEPLOY_RENDER.md`
- `templates/help.html`
- `templates/email_outbox.html`
- `templates/portfolio_report.html`
- `templates/client_report.html`
- `templates/readiness_request.html`
- `templates/backup_restore.html`
- `templates/integrations.html`

## New documentation
- `PRICING_AND_LAUNCH_V2_46_12.md`
- `EARLY_CUSTOMER_DEPLOYMENT_V2_46_12.md`
- `IT_UPGRADE_PLAN_V2_46_12.md`

## Behavior impact
No operational workflow behavior change. This is a launch/hosting/configuration and wording cleanup release.

## Important deployment note
For an existing Render service, preserve the current persistent disk. `render.yaml` is the desired template for new deployments; do not delete/recreate an existing disk simply to make it match the Blueprint.
