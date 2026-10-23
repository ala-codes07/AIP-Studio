"""Offline, zero-subscription Search Console CSV evidence and opportunity analysis.

No Google authentication or unofficial scraping: users download the *Queries*
CSV from their own Search Console account and upload it. No metrics invented.
"""
from __future__ import annotations
import csv
import io
import math
import re
import unicodedata
from typing import Any

from app.core.exceptions import ValidationError

MAX_CSV_BYTES = 2_000_000
MAX_ROWS = 3000


def parse_queries_csv(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > MAX_CSV_BYTES:
        raise ValidationError("Search Console CSV must be between 1 byte and 2 MB.")
    try:
        decoded = raw.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValidationError("Please export the Search Console CSV as UTF-8.") from exc
    try:
        dialect = csv.Sniffer().sniff(decoded[:4096], delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    lines = io.StringIO(decoded, newline='')
    reader = csv.DictReader(lines, dialect=dialect)
    if not reader.fieldnames:
        raise ValidationError("CSV requires a header row: Query, Clicks, Impressions, CTR, Position.")
    aliases = {
        'query': {'query', 'queries', 'top queries', 'search query', 'keyword', 'الاستعلامات', 'أهم طلبات البحث', 'عبارات البحث', 'جستجوهای برتر', 'عبارت جستجو'},
        'clicks': {'clicks', 'النقرات', 'کلیک', 'کلیک‌ها'},
        'impressions': {'impressions', 'مرات الظهور', 'عدد الظهور', 'نمایش‌ها', 'نمایش'},
        'ctr': {'ctr', 'site ctr', 'نسبة النقر إلى الظهور', 'نرخ کلیک'},
        'position': {'position', 'average position', 'متوسط موضع الظهور', 'الموضع', 'موضع', 'میانگین رتبه'},
    }
    columns = {}
    for key, accepted in aliases.items():
        for column in reader.fieldnames:
            if column and column.strip().lower().lstrip('\ufeff') in accepted:
                columns[key] = column
                break
    if len(columns) != len(aliases):
        raise ValidationError("Select the Search Console 'Queries' table export with Query, Clicks, Impressions, CTR and Position columns.")
    rows: list[dict[str, Any]] = []
    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            raise ValidationError("CSV contains too many rows (maximum 3,000).")
        try:
            query = (row[columns['query']] or '').strip()[:180]
            clicks = int((row[columns['clicks']] or '').strip().replace(',', ''))
            impressions = int((row[columns['impressions']] or '').strip().replace(',', ''))
            raw_ctr = (row[columns['ctr']] or '').strip().replace(',', '.').replace('٫','.').replace('٪','%')
            ctr = float(raw_ctr.rstrip('%'))
            if '%' in raw_ctr or ctr > 1:
                ctr /= 100
            position = float((row[columns['position']] or '').strip().replace(',', '.').replace('٫','.'))
            if not query or query.lstrip().startswith(('=', '+', '-', '@')) or any(ord(ch) < 32 for ch in query) or not (0 <= clicks <= impressions <= 1_000_000_000) or not (0 <= ctr <= 1) or not (1 <= position <= 1000):
                raise ValueError('Bad row')
            if not math.isfinite(position) or not math.isfinite(ctr):
                raise ValueError('Non-finite number')
        except (TypeError, KeyError, ValueError, OverflowError) as exc:
            raise ValidationError(f"Invalid Search Console CSV data at row {i+2}.") from exc
        rows.append({'query': query, 'clicks': clicks, 'impressions': impressions, 'ctr': round(ctr, 5), 'position': round(position, 2)})
    if not rows:
        raise ValidationError("No query rows found in the CSV.")
    # Duplicated queries in exports cause misleading aggregation: reject rather than sum
    # rows that may describe overlapping date ranges or dimensions.
    if len({r['query'].casefold() for r in rows}) != len(rows):
        raise ValidationError("CSV has duplicate query rows. Export a single Queries report without merged tables.")
    return {'rows': rows, 'row_count': len(rows), 'total_clicks': sum(r['clicks'] for r in rows),
            'total_impressions': sum(r['impressions'] for r in rows),
            'scope': "Uploaded Search Console Queries CSV; period and domain property cannot be independently verified."}


# GSC Queries exports contain NO landing-page URLs. Matching below is an
# editorial heuristic against fetched HTML, never a verified attribution.
_QUERY_STOP = {"و", "در", "به", "از", "برای", "با", "که", "را", "روی", "این", "آن", "یک",
               "the", "and", "for", "of", "in", "on", "to", "a", "an", "is"}
_WORD = re.compile(r"[^\W\d_]{2,}", re.UNICODE)


def _terms(text: str) -> set[str]:
    text = unicodedata.normalize("NFKC", str(text or "")).casefold()
    text = text.replace("ي", "ی").replace("ك", "ک").replace("ـ", "").replace("\u200c", " ")
    text = re.sub(r"[\u064b-\u065f]", "", text)
    words = _WORD.findall(text)
    # Persian pages frequently use both «تولید کننده» and «تولیدکننده».
    if "تولید" in words and "کننده" in words:
        words += ["تولیدکننده"]
    if "تولیدکننده" in words:
        words += ["تولید", "کننده"]
    return {w for w in words if w not in _QUERY_STOP and len(w) <= 50}


def _page_match(query: str, pages: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str, str]:
    wanted = _terms(query)
    if not wanted or not pages:
        return None, "none", "No fetched page evidence is available."
    ranking: list[tuple[float, int, dict[str, Any]]] = []
    for page in pages:
        if not isinstance(page, dict) or not page.get("url"):
            continue
        main = _terms(" ".join([str(page.get("title", "")),
                                *(str(h) for h in page.get("h1", []) if isinstance(h, str))]))
        support = _terms(" ".join([str(page.get("description", "")),
                                   *(str(h) for h in page.get("h2", []) if isinstance(h, str)),
                                   *(str(k.get("term", "")) for k in page.get("keywords", []) if isinstance(k, dict))]))
        main_hits = len(wanted & main)
        extra_hits = len((wanted & support) - main)
        total = main_hits + extra_hits
        if total:
            ranking.append((round(2.0 * main_hits + 0.75 * extra_hits, 3), total, page))
    if not ranking:
        return None, "none", "No overlapping terms in fetched headings or page summaries."
    ranking.sort(key=lambda x: (-x[0], -x[1], str(x[2].get("url", ""))))
    best_score, hit_count, best = ranking[0]
    runner_score = ranking[1][0] if len(ranking) > 1 else 0
    coverage = hit_count / len(wanted)
    margin = best_score - runner_score
    if len(wanted) >= 2 and coverage >= .8 and margin >= 1.5 and best_score >= 4:
        confidence = "strong_candidate"
    elif len(wanted) >= 2 and coverage >= .5 and margin >= 1.5 and best_score >= 3:
        confidence = "possible_candidate"
    else:
        confidence = "ambiguous"
    # Return the candidate even when ambiguous, but callers must not present it
    # as the actual Google landing URL.
    note = (f"{hit_count}/{len(wanted)} query terms overlapped scanned headings or summaries; "
            f"candidate separation {margin:.1f}. Queries export does not identify landing URLs.")
    return best, confidence, note


def opportunities(rows: list[dict[str, Any]], pages: list[dict[str, Any]] | None = None,
                  findings: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Rank transparent GSC + on-page review ideas without pretending to know SERP landing URLs.

    `pages` and `findings` are from the latest usable audit *of the same site*.
    User-supplied clicks/impressions/position are never synthesized or changed.
    """
    pages = pages or []
    findings = findings or []
    results = []
    for row in rows:
        query = str(row['query'])
        candidate, confidence, match_note = _page_match(query, pages)
        impressions, clicks, position, ctr = (row['impressions'], row['clicks'],
                                             row['position'], row['ctr'])
        relevant = []
        if candidate and confidence in ('strong_candidate', 'possible_candidate'):
            relevant = [f for f in findings if isinstance(f, dict) and
                        f.get('page_url') == candidate['url'] and
                        f.get('rule') in {'missing_title', 'long_title', 'missing_description',
                                          'long_description', 'missing_h1', 'multiple_h1',
                                          'noindex', 'xrobots_noindex', 'canonical_conflict'}]
        relevant.sort(key=lambda f: {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}.get(f.get('severity'), 4))
        review = []
        if impressions < 10:
            label = 'Low sample'
            review.append('Fewer than 10 impressions in this export; compare a longer, equivalent date window first.')
        elif position > 25:
            label = 'Visibility review'
            review.append(f'Average position {position:.1f} indicates limited visibility in this export. Check intent fit and topical coverage before changing the snippet; zero clicks alone does not prove a CTR issue.')
        elif position > 10:
            label = 'Page relevance review'
            review.append('Review coverage of this query in the page heading, useful body content and contextual internal links; check the actual landing page in Search Console.')
        elif ctr < .02 and impressions >= 30:
            label = 'Snippet review'
            review.append('Position is within the first 10 on average, but CTR is below 2% in this export. Compare intent and actual search snippets before editing titles or descriptions.')
        else:
            label = 'Monitor'
            review.append('Observe clicks and position across comparable date ranges; do not change content based only on a small snapshot.')

        if confidence in ('strong_candidate', 'possible_candidate') and candidate:
            review.append(f'Potential page to review: {candidate["url"]} (inferred from HTML headings, NOT a verified GSC landing page).')
            if relevant:
                issue = relevant[0]
                review.append(f'Existing audit finding on that page: {issue.get("title", "issue")}. {issue.get("recommendation", "")}')
            elif isinstance(candidate.get('word_count'), int) and candidate['word_count'] < 160:
                review.append(f'This candidate has {candidate["word_count"]} extracted substantive words. Check whether it answers visitor intent; short product pages are not automatically defective.')
            else:
                review.append('Check whether the existing page clearly answers this query; verify the actual landing URL in the GSC Pages report.')
        else:
            review.append('No uniquely supported landing-page match in the scanned pages. Check the GSC Pages report (preferably query-filtered) to identify the actual landing URL.')
            if any(t in _terms(query) for t in ('قیمت', 'هزینه', 'price', 'cost')):
                review.append('For pricing intent, assess whether the site explains estimates and pricing factors accurately; do not invent prices.')
            elif any(t in _terms(query) for t in ('تهران', 'اصفهان', 'کرج', 'مشهد', 'north')):
                review.append('For location intent, clarify real service coverage only where the business actually operates.')

        priority = round(impressions * (1 - ctr) / (1 + max(position - 1, 0) / 10), 1)
        results.append({**row, 'type': label, 'priority_index': priority,
                        'matched_page': candidate['url'] if candidate and confidence in ('strong_candidate', 'possible_candidate') else None,
                        'candidate_page': candidate['url'] if candidate else None,
                        'page_match_confidence': confidence, 'page_match_evidence': match_note,
                        'related_audit_findings': [{'title': f.get('title', ''), 'severity': f.get('severity', '')} for f in relevant[:2]],
                        'recommendation': ' '.join(review)})
    return sorted(results, key=lambda r: (-r['priority_index'], -r['impressions'], r['query']))[:40]
