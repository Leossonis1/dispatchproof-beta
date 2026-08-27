# DispatchProof V1.5.1 — Free Render Beta

V1.5.1 makes free-tier email testing intentional.

## Free Beta · Outbox Mode

The Render Blueprint now sets:

`DISPATCHPROOF_EMAIL_MODE=outbox`

In this mode:

- Readiness emails are generated and logged in Email Outbox.
- Reminder previews are generated and logged in Email Outbox.
- Nothing is sent externally.
- SMTP is never attempted.
- Automatic email reminder delivery is paused.
- Existing Gmail SMTP environment variables can remain in Render; they are ignored while Outbox Mode is active.

The public readiness-link workflow continues to work normally.

## Later

When we decide to enable real outbound email, we can use an HTTPS email API
or an SMTP-capable hosting plan and explicitly switch email mode.
