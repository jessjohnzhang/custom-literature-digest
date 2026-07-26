---
name: custom-literature-digest
description: Configure and operate a personalized scholarly-literature monitor with journal and topic filtering, recurring searches, deduplication, an interactive dashboard, weekly executive digests, and authorized email delivery. Use when a user wants to set up, change, run, troubleshoot, or review automated paper monitoring, literature alerts, research digests, journal watchlists, or the bundled EV-charging literature profile.
---

# Custom Literature Digest

Build a source-grounded literature alert from user-selected journals and topics. Never imply that a skill runs continuously by itself: recurring execution requires Codex automations, and sending email requires an authorized Gmail or Outlook connector.

## Select the workflow

- For first-time setup or changed preferences, run **Configure**.
- For a manual refresh, run **Search**.
- For a dashboard or digest, run **Generate**.
- For recurring operation, run **Schedule**.
- For email delivery, run **Deliver** only after the user reviews recipients and authorizes the provider.

## Configure

1. Ask one concise question at a time for profile name, journals, topics, search frequency, digest schedule, timezone, recipient email, provider, and dashboard visibility.
2. Offer `presets/ev-charging.json` when the user wants the bundled EV profile.
3. Show the complete proposed configuration and obtain confirmation before writing it or creating automations.
4. Copy the preset or create JSON matching `references/configuration-schema.md`.
5. Keep personal configuration outside the skill repository. Default to a task-local `literature-data/<profile>/config.json`.
6. Validate:

```bash
python scripts/literature_intelligence.py validate --config /absolute/path/config.json
```

## Search

Run a bounded incremental search:

```bash
python scripts/literature_intelligence.py search \
  --config /absolute/path/config.json \
  --state /absolute/path/state.db \
  --from-date YYYY-MM-DD --until-date YYYY-MM-DD
```

The script queries Crossref, enforces the configured journal list, classifies topics, and deduplicates by DOI or normalized title. Treat API results as candidate metadata, not proof of relevance. Do not invent missing abstracts or findings.

## Generate

Generate a self-contained dashboard and weekly report:

```bash
python scripts/literature_intelligence.py generate \
  --config /absolute/path/config.json \
  --state /absolute/path/state.db \
  --from-date YYYY-MM-DD --until-date YYYY-MM-DD \
  --output-dir /absolute/path/output
```

Return links to `dashboard.html`, `weekly-report.html`, and `weekly-report.txt`. Explain that topic counts are multi-label and may exceed the unique-paper total.

## Schedule

Read `references/automation-and-email.md` before creating, updating, or deleting automations.

Create two timezone-aware recurring automations only after confirmation:

1. An incremental search using the last successful checkpoint with a small overlap.
2. A digest generation at the selected day and time.

Use the product automation tool rather than writing raw directives. Preserve the user's local time across daylight-saving changes. Report exact schedules after creation.

## Deliver

Read `references/automation-and-email.md`. Generate the report before sending. Show recipient(s), subject, reporting window, and attachment/link behavior. Use an authorized Gmail or Outlook connector; never request or store a password or token. Record successful delivery in state and avoid duplicate sends unless the user explicitly asks to resend.

If the required connector is unavailable, explain that the report was still generated and offer to connect Gmail or Outlook. Do not claim delivery without tool confirmation.

## Quality rules

- Match canonical journal titles or configured aliases; quarantine ambiguous matches.
- Include generic AI, optimisation, or transport papers only when materially applied to a configured research area.
- Use abstracts and metadata as the only evidence for summaries.
- Label metadata-only entries when no abstract is available.
- Link to the DOI resolver or publisher landing page.
- Sanitize all HTML rendered by the scripts.
- Generate a valid zero-results dashboard and report when nothing qualifies.
- Preserve state on partial API failure and report the failure.

Read `references/source-policy.md` when changing sources, relevance rules, or summary behavior.
