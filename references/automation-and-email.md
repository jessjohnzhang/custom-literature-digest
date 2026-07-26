# Automation and email

## Automations

Create separate recurring tasks for search and digest generation. Use absolute paths in task prompts. The search task runs `search` for the overlap window and reports failures. The digest task runs `generate`, then requests authorized delivery.

Always use the Codex automation tool. Ask before creating or changing schedules. Use the configured IANA timezone so Friday 17:00 remains local time across daylight-saving changes.

## Email

Use a connected Gmail or Outlook tool. Do not put passwords, OAuth tokens, or connector data in config files. Before sending, show:

- To/Cc recipients
- Subject
- Reporting dates
- Whether the dashboard is attached, local-only, or publicly linked

Send `weekly-report.html` as the HTML body and retain `weekly-report.txt` as fallback. Claim success only when the connector confirms it. If unavailable, preserve the files and offer connection.
