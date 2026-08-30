# Early Customer Deployment Checklist — Isolated Company Model

Use this process for the first paying/founding customers.

## Rule

**One unrelated customer company = one isolated DispatchProof deployment + database + upload store.**

Do not create unrelated companies as users inside the same V2.46.12 database.

## Before onboarding

- Create/clone a dedicated Render service for the customer.
- Use the paid `0.5c-512mb` compute plan.
- Attach a dedicated persistent disk.
- Set `DISPATCHPROOF_DATA_DIR=/var/data/dispatchproof`.
- Set `DISPATCHPROOF_DEPLOYMENT_MODE=isolated-company`.
- Generate a unique `DISPATCHPROOF_SECRET_KEY`.
- Set a unique private Owner/Admin password.
- Set the customer company name/timezone/email configuration.
- Never copy another customer's live database or uploads into the new instance.

## After onboarding

- Verify `/health` reports `2.46.12` and `isolated-company`.
- Create the customer's real users and roles.
- Run fresh-user QA.
- Verify one mobile browser.
- Verify backup/export.
- Record the service name, customer, subscription start, and deployment date in the owner operations log.

## Capacity policy

The isolated model is appropriate for the first handful of customers because it maximizes data separation and minimizes architectural risk. Reassess shared SaaS architecture at 3–5 paying companies or sooner if operating multiple deployments becomes burdensome.
