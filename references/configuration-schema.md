# Configuration schema

Use UTF-8 JSON. Required top-level keys:

- `profile_name`: non-empty string.
- `journals`: non-empty array of `{name, aliases}` objects.
- `topics`: non-empty array of `{name, terms}` objects.
- `required_context_terms`: terms proving that method-only matches concern the monitored domain.
- `search`: `frequency`, `lookback_days`, and `rows_per_journal`.
- `digest`: `frequency`, lowercase `weekday`, `HH:MM` local `time`, and IANA `timezone`.
- `delivery`: `provider` (`gmail`, `outlook`, or `none`) and `recipients`.
- `dashboard.visibility`: `local` or `github-pages`.

Personal configurations must not be committed. Start from `presets/ev-charging.json`, save a copy in a user-data directory, then edit the copy.
