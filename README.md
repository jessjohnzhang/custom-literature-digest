<h1>
  <img src="assets/logo-400.png" width="52" height="52" align="absmiddle" alt="Custom Literature Digest logo">
  Custom Literature Digest
</h1>

An installable Codex skill for monitoring selected journals and research topics, generating an interactive literature dashboard, and preparing scheduled email digests.

The included EV-charging preset watches leading energy and transport journals for infrastructure planning, forecasting, utilisation, resilience, flexibility, smart charging, V2G/V2X, and relevant AI/optimisation/spatial methods.

## Install

Clone this repository into your Codex skills directory, or copy the repository folder there. Restart or reload Codex, then ask:

> Use `$custom-literature-digest` to configure my weekly literature monitor.

The skill asks for journals, topics, schedules, timezone, recipient email, provider, and dashboard visibility. Personal configuration and generated data stay outside Git.

## Manual demo

```bash
cp presets/ev-charging.json /tmp/ev-literature.json
python scripts/literature_intelligence.py validate --config /tmp/ev-literature.json
python scripts/literature_intelligence.py import-fixture \
  --config /tmp/ev-literature.json --state /tmp/ev-literature.db \
  --fixture tests/fixtures/crossref.json
python scripts/literature_intelligence.py generate \
  --config /tmp/ev-literature.json --state /tmp/ev-literature.db \
  --from-date 2026-07-01 --until-date 2026-07-31 --output-dir /tmp/ev-report
```

## Automation boundary

A skill does not run continuously on its own. Codex recurring automations execute searches and digests. Automatic email requires each user to authorize Gmail or Outlook. The skill guides both steps and never stores passwords or OAuth tokens.

## Data source

The default backend is the official Crossref REST API. Results are filtered locally against canonical journal names and configured topic evidence. Missing abstracts are labeled rather than fabricated.

## Test

```bash
python -m unittest discover -s tests -v
python /path/to/skill-creator/scripts/quick_validate.py .
```
