#!/usr/bin/env python3
"""Custom literature monitoring using only the Python standard library."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sqlite3
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

API_URL = "https://api.crossref.org/works"
USER_AGENT = "custom-literature-digest/0.1 (mailto:anonymous@example.invalid)"


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def strip_markup(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def load_config(path: str | Path) -> dict:
    with Path(path).open(encoding="utf-8") as handle:
        config = json.load(handle)
    errors = validate_config(config)
    if errors:
        raise ValueError("\n".join(errors))
    return config


def validate_config(config: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(config.get("profile_name"), str) or not config["profile_name"].strip():
        errors.append("profile_name must be a non-empty string")
    journals = config.get("journals")
    if not isinstance(journals, list) or not journals:
        errors.append("journals must be a non-empty array")
    elif any(not isinstance(j, dict) or not str(j.get("name", "")).strip() for j in journals):
        errors.append("each journal must contain a non-empty name")
    topics = config.get("topics")
    if not isinstance(topics, list) or not topics:
        errors.append("topics must be a non-empty array")
    elif any(
        not isinstance(t, dict)
        or not str(t.get("name", "")).strip()
        or not isinstance(t.get("terms"), list)
        or not t["terms"]
        for t in topics
    ):
        errors.append("each topic must contain a name and non-empty terms array")
    digest = config.get("digest", {})
    try:
        ZoneInfo(str(digest.get("timezone", "")))
    except ZoneInfoNotFoundError:
        errors.append("digest.timezone must be a valid IANA timezone")
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", str(digest.get("time", ""))):
        errors.append("digest.time must use HH:MM")
    if digest.get("weekday") not in {
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
    }:
        errors.append("digest.weekday must be a lowercase weekday")
    delivery = config.get("delivery", {})
    if delivery.get("provider") not in {"gmail", "outlook", "none"}:
        errors.append("delivery.provider must be gmail, outlook, or none")
    for address in delivery.get("recipients", []):
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(address)):
            errors.append(f"invalid recipient email: {address}")
    return errors


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS papers (
          paper_key TEXT PRIMARY KEY,
          doi TEXT,
          title TEXT NOT NULL,
          authors_json TEXT NOT NULL,
          journal TEXT NOT NULL,
          published TEXT NOT NULL,
          abstract TEXT NOT NULL,
          url TEXT NOT NULL,
          topics_json TEXT NOT NULL,
          evidence_json TEXT NOT NULL,
          discovered_at TEXT NOT NULL,
          raw_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY,
          kind TEXT NOT NULL,
          started_at TEXT NOT NULL,
          completed_at TEXT,
          status TEXT NOT NULL,
          detail TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS deliveries (
          delivery_key TEXT PRIMARY KEY,
          delivered_at TEXT NOT NULL,
          provider TEXT NOT NULL,
          recipients_json TEXT NOT NULL
        );
        """
    )


def date_from_parts(item: dict) -> str:
    for key in ("published-online", "published-print", "published", "issued", "created"):
        parts = item.get(key, {}).get("date-parts", [])
        if parts and parts[0]:
            values = list(parts[0]) + [1, 1]
            try:
                return dt.date(int(values[0]), int(values[1]), int(values[2])).isoformat()
            except (TypeError, ValueError):
                continue
    return ""


def authors_from_item(item: dict) -> list[str]:
    authors = []
    for author in item.get("author", []):
        name = " ".join(
            part.strip() for part in (str(author.get("given", "")), str(author.get("family", ""))) if part.strip()
        )
        if name:
            authors.append(name)
    return authors


def configured_journal(item: dict, config: dict) -> str | None:
    candidates = [str(x) for x in item.get("container-title", []) if x]
    known: dict[str, str] = {}
    for journal in config["journals"]:
        canonical = journal["name"]
        for alias in [canonical, *journal.get("aliases", [])]:
            known[normalized(alias)] = canonical
    for candidate in candidates:
        key = normalized(candidate)
        if key in known:
            return known[key]
    return None


def classify(item: dict, config: dict) -> tuple[list[str], dict[str, list[str]]]:
    title = " ".join(str(x) for x in item.get("title", []))
    abstract = strip_markup(item.get("abstract"))
    haystack = normalized(f"{title} {abstract}")
    context_terms = [normalized(x) for x in config.get("required_context_terms", [])]
    context_found = any(term and term in haystack for term in context_terms)
    method_markers = {
        "machine learning", "artificial intelligence", "deep learning",
        "optimization", "optimisation", "spatial analysis", "geospatial"
    }
    labels: list[str] = []
    evidence: dict[str, list[str]] = {}
    for topic in config["topics"]:
        matches = [term for term in topic["terms"] if normalized(term) in haystack]
        if not matches:
            continue
        only_generic = all(normalized(term) in method_markers for term in matches)
        if only_generic and not context_found:
            continue
        labels.append(topic["name"])
        evidence[topic["name"]] = matches
    return labels, evidence


def paper_from_item(item: dict, config: dict) -> dict | None:
    journal = configured_journal(item, config)
    if not journal:
        return None
    topics, evidence = classify(item, config)
    if not topics:
        return None
    title = strip_markup(" ".join(str(x) for x in item.get("title", [])))
    if not title:
        return None
    doi = str(item.get("DOI", "")).lower().strip()
    published = date_from_parts(item)
    url = f"https://doi.org/{urllib.parse.quote(doi, safe='/')}" if doi else str(item.get("URL", ""))
    fallback = f"{normalized(title)}|{normalized(journal)}|{published[:4]}"
    return {
        "paper_key": doi or hashlib.sha256(fallback.encode()).hexdigest(),
        "doi": doi,
        "title": title,
        "authors": authors_from_item(item),
        "journal": journal,
        "published": published,
        "abstract": strip_markup(item.get("abstract")),
        "url": url,
        "topics": topics,
        "evidence": evidence,
        "raw": item,
    }


def upsert_papers(connection: sqlite3.Connection, papers: list[dict]) -> int:
    before = connection.total_changes
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    for paper in papers:
        connection.execute(
            """
            INSERT INTO papers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_key) DO UPDATE SET
              doi=excluded.doi, title=excluded.title, authors_json=excluded.authors_json,
              journal=excluded.journal, published=excluded.published, abstract=excluded.abstract,
              url=excluded.url, topics_json=excluded.topics_json,
              evidence_json=excluded.evidence_json, raw_json=excluded.raw_json
            """,
            (
                paper["paper_key"], paper["doi"], paper["title"], json.dumps(paper["authors"]),
                paper["journal"], paper["published"], paper["abstract"], paper["url"],
                json.dumps(paper["topics"]), json.dumps(paper["evidence"]), now,
                json.dumps(paper["raw"]),
            ),
        )
    connection.commit()
    return connection.total_changes - before


def crossref_items(journal: str, start: str, end: str, rows: int) -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "query.container-title": journal,
            "filter": f"from-pub-date:{start},until-pub-date:{end},type:journal-article",
            "rows": min(max(rows, 1), 1000),
            "select": "DOI,title,author,container-title,published-online,published-print,published,issued,created,abstract,URL",
            "mailto": "anonymous@example.invalid",
        }
    )
    request = urllib.request.Request(f"{API_URL}?{params}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return payload["message"]["items"]


def run_search(config: dict, state_path: Path, start: str, end: str) -> tuple[int, int]:
    connection = sqlite3.connect(state_path)
    init_db(connection)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    run_id = connection.execute(
        "INSERT INTO runs(kind, started_at, status, detail) VALUES ('search', ?, 'running', '')",
        (started,),
    ).lastrowid
    connection.commit()
    candidates: list[dict] = []
    try:
        rows = int(config.get("search", {}).get("rows_per_journal", 100))
        for journal in config["journals"]:
            for item in crossref_items(journal["name"], start, end, rows):
                paper = paper_from_item(item, config)
                if paper:
                    candidates.append(paper)
        unique = {paper["paper_key"]: paper for paper in candidates}
        changes = upsert_papers(connection, list(unique.values()))
        connection.execute(
            "UPDATE runs SET completed_at=?, status='ok', detail=? WHERE id=?",
            (dt.datetime.now(dt.timezone.utc).isoformat(), f"{len(unique)} included; {changes} database changes", run_id),
        )
        connection.commit()
        return len(unique), changes
    except Exception as exc:
        connection.execute(
            "UPDATE runs SET completed_at=?, status='failed', detail=? WHERE id=?",
            (dt.datetime.now(dt.timezone.utc).isoformat(), str(exc), run_id),
        )
        connection.commit()
        raise
    finally:
        connection.close()


def read_papers(connection: sqlite3.Connection, start: str, end: str) -> list[dict]:
    rows = connection.execute(
        """SELECT paper_key, doi, title, authors_json, journal, published, abstract,
                  url, topics_json, evidence_json
           FROM papers WHERE published BETWEEN ? AND ? ORDER BY published DESC, title""",
        (start, end),
    ).fetchall()
    keys = ("paper_key", "doi", "title", "authors", "journal", "published", "abstract", "url", "topics", "evidence")
    papers = []
    for row in rows:
        paper = dict(zip(keys, row))
        for field in ("authors", "topics", "evidence"):
            paper[field] = json.loads(paper[field])
        papers.append(paper)
    return papers


def concise_summary(paper: dict) -> str:
    if not paper["abstract"]:
        return "Metadata-only; contribution could not be summarized from the available record."
    sentences = re.split(r"(?<=[.!?])\s+", paper["abstract"])
    contribution = " ".join(sentences[:2]).strip()
    relevance = ", ".join(paper["topics"])
    return f"{contribution} Relevant to: {relevance}."


def render_report(config: dict, papers: list[dict], start: str, end: str) -> tuple[str, str]:
    topic_groups: dict[str, list[dict]] = defaultdict(list)
    for paper in papers:
        for topic in paper["topics"]:
            topic_groups[topic].append(paper)
    ranked = sorted(topic_groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))
    takeaways = [
        f"{topic} was represented by {len(items)} new paper{'s' if len(items) != 1 else ''}."
        for topic, items in ranked[:10]
    ]
    if not takeaways:
        takeaways = ["No qualifying new papers were found in the configured journals and topics."]
    html_parts = [
        f"<h1>{html.escape(config['profile_name'])}</h1>",
        f"<p>Reporting period: {start} to {end}. {len(papers)} unique new papers.</p>",
        "<h2>Executive summary</h2><ul>",
        *[f"<li>{html.escape(x)}</li>" for x in takeaways],
        "</ul><h2>Papers by topic</h2>",
    ]
    text_parts = [
        config["profile_name"], f"Reporting period: {start} to {end}",
        f"{len(papers)} unique new papers.", "", "EXECUTIVE SUMMARY",
        *[f"- {x}" for x in takeaways], "", "PAPERS BY TOPIC",
    ]
    seen: set[tuple[str, str]] = set()
    for topic, items in ranked:
        html_parts.append(f"<h3>{html.escape(topic)} ({len(items)})</h3>")
        text_parts.extend(["", f"{topic} ({len(items)})"])
        for paper in items:
            marker = (topic, paper["paper_key"])
            if marker in seen:
                continue
            seen.add(marker)
            summary = concise_summary(paper)
            authors = ", ".join(paper["authors"]) or "Authors unavailable"
            safe_url = html.escape(paper["url"], quote=True)
            html_parts.append(
                f"<article><h4><a href=\"{safe_url}\">{html.escape(paper['title'])}</a></h4>"
                f"<p>{html.escape(authors)} · {html.escape(paper['journal'])} · "
                f"{html.escape(paper['published'] or 'Date unavailable')}</p>"
                f"<p>{html.escape(summary)}</p></article>"
            )
            text_parts.extend([
                f"- {paper['title']}", f"  {authors}; {paper['journal']}; {paper['published'] or 'Date unavailable'}",
                f"  {summary}", f"  {paper['url']}",
            ])
    html_parts.extend(["<h2>Emerging trends</h2>", "<p>", html.escape(" ".join(takeaways)), "</p>"])
    text_parts.extend(["", "EMERGING TRENDS", " ".join(takeaways)])
    return "\n".join(html_parts), "\n".join(text_parts)


def render_dashboard(config: dict, papers: list[dict], start: str, end: str) -> str:
    topic_counts = Counter(topic for paper in papers for topic in paper["topics"])
    journal_counts = Counter(paper["journal"] for paper in papers)
    cards = []
    for paper in papers:
        searchable = normalized(" ".join([paper["title"], *paper["authors"]]))
        topic_attr = "|".join(paper["topics"])
        cards.append(
            f"""<article class="card" data-journal="{html.escape(paper['journal'], quote=True)}"
 data-topics="{html.escape(topic_attr, quote=True)}" data-date="{html.escape(paper['published'], quote=True)}"
 data-search="{html.escape(searchable, quote=True)}" tabindex="0">
 <div class="labels">{''.join(f'<span>{html.escape(t)}</span>' for t in paper['topics'])}</div>
 <h2><a href="{html.escape(paper['url'], quote=True)}" target="_blank" rel="noopener">{html.escape(paper['title'])}</a></h2>
 <p>{html.escape(', '.join(paper['authors']) or 'Authors unavailable')}</p>
 <p><strong>{html.escape(paper['journal'])}</strong> · {html.escape(paper['published'] or 'Date unavailable')}</p>
 <details><summary>Abstract</summary><p>{html.escape(paper['abstract'] or 'Abstract unavailable; metadata-only record.')}</p></details>
</article>"""
        )
    journal_options = "".join(
        f'<option value="{html.escape(j["name"], quote=True)}">{html.escape(j["name"])}</option>'
        for j in config["journals"]
    )
    topic_options = "".join(
        f'<option value="{html.escape(t["name"], quote=True)}">{html.escape(t["name"])}</option>'
        for t in config["topics"]
    )
    stats = {
        "topics": dict(topic_counts),
        "journals": dict(journal_counts),
    }
    stats_json = json.dumps(stats).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(config['profile_name'])}</title>
<style>
:root{{--ink:#17212b;--muted:#65727e;--paper:#f4f7f5;--card:#fff;--accent:#087f5b}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 system-ui,sans-serif}}
header{{padding:2.5rem max(5vw,1rem);background:#12372a;color:white}}main{{padding:1.5rem max(5vw,1rem)}}
.summary,.filters{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:1rem;margin-bottom:1.5rem}}
.metric,.card,.filters label{{background:var(--card);padding:1rem;border-radius:14px;box-shadow:0 4px 18px #0001}}
.metric b{{display:block;font-size:1.7rem;color:var(--accent)}}input,select{{display:block;width:100%;margin-top:.35rem;padding:.65rem}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:1rem}}.card h2{{font-size:1.15rem}}
.labels span{{display:inline-block;background:#d8f3e7;color:#075c42;padding:.2rem .5rem;border-radius:99px;margin:.15rem;font-size:.75rem}}
a{{color:#096a50}}.card[hidden]{{display:none}}small{{color:var(--muted)}}
</style></head><body><header><h1>{html.escape(config['profile_name'])}</h1>
<p>{start} to {end} · Last generated {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p></header>
<main><section class="summary"><div class="metric"><b id="total">{len(papers)}</b>papers shown</div>
<div class="metric"><b>{len(topic_counts)}</b>active topics</div><div class="metric"><b>{len(journal_counts)}</b>active journals</div>
<div class="metric"><b>{html.escape(topic_counts.most_common(1)[0][0] if topic_counts else 'None')}</b>most active topic</div></section>
<section class="filters"><label>Journal<select id="journal"><option value="">All</option>{journal_options}</select></label>
<label>Topic<select id="topic"><option value="">All</option>{topic_options}</select></label>
<label>From date<input id="from" type="date" value="{start}"></label><label>To date<input id="to" type="date" value="{end}"></label>
<label>Title or author<input id="query" type="search" placeholder="Search"></label></section>
<small>Topic counts are multi-label and may exceed the number of unique papers.</small>
<section class="grid" id="cards">{''.join(cards)}</section></main>
<script>
const stats={stats_json};
const controls=[...document.querySelectorAll("input,select")],cards=[...document.querySelectorAll(".card")];
function filter(){{const j=document.querySelector("#journal").value,t=document.querySelector("#topic").value,
f=document.querySelector("#from").value,u=document.querySelector("#to").value,q=document.querySelector("#query").value.toLowerCase();
let n=0;cards.forEach(c=>{{let ok=(!j||c.dataset.journal===j)&&(!t||c.dataset.topics.split("|").includes(t))&&
(!f||c.dataset.date>=f)&&(!u||c.dataset.date<=u)&&(!q||c.dataset.search.includes(q));c.hidden=!ok;if(ok)n++}});
document.querySelector("#total").textContent=n}}controls.forEach(x=>x.addEventListener("input",filter));
</script></body></html>"""


def generate(config: dict, state_path: Path, start: str, end: str, output_dir: Path) -> list[Path]:
    connection = sqlite3.connect(state_path)
    init_db(connection)
    papers = read_papers(connection, start, end)
    connection.close()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_html, report_text = render_report(config, papers, start, end)
    files = [
        output_dir / "dashboard.html",
        output_dir / "weekly-report.html",
        output_dir / "weekly-report.txt",
    ]
    files[0].write_text(render_dashboard(config, papers, start, end), encoding="utf-8")
    files[1].write_text(report_html, encoding="utf-8")
    files[2].write_text(report_text, encoding="utf-8")
    return files


def import_fixture(config: dict, state_path: Path, fixture: Path) -> int:
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    items = payload.get("message", {}).get("items", payload if isinstance(payload, list) else [])
    papers = [paper for item in items if (paper := paper_from_item(item, config))]
    connection = sqlite3.connect(state_path)
    init_db(connection)
    upsert_papers(connection, papers)
    connection.close()
    return len(papers)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--config", required=True)
    for name in ("search", "generate"):
        command = sub.add_parser(name)
        command.add_argument("--config", required=True)
        command.add_argument("--state", required=True)
        command.add_argument("--from-date", required=True)
        command.add_argument("--until-date", required=True)
        if name == "generate":
            command.add_argument("--output-dir", required=True)
    fixture = sub.add_parser("import-fixture")
    fixture.add_argument("--config", required=True)
    fixture.add_argument("--state", required=True)
    fixture.add_argument("--fixture", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = load_config(args.config)
        if args.command == "validate":
            print("Configuration is valid.")
        elif args.command == "search":
            included, changes = run_search(
                config, Path(args.state), args.from_date, args.until_date
            )
            print(f"Included {included} unique papers; {changes} database changes.")
        elif args.command == "generate":
            for path in generate(
                config, Path(args.state), args.from_date, args.until_date, Path(args.output_dir)
            ):
                print(path.resolve())
        elif args.command == "import-fixture":
            count = import_fixture(config, Path(args.state), Path(args.fixture))
            print(f"Imported {count} qualifying papers.")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
