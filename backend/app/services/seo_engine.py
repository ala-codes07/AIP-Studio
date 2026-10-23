"""Bounded, public-internet SEO crawler and deterministic evidence checks.

Safety: DNS resolution is validated and the outbound socket is pinned to the
validated public IP. Redirects are revalidated. Only public HTTP(S) port 80/443,
HTML responses, and a small same-host page budget are permitted.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from html.parser import HTMLParser
import http.client
import ipaddress
import json
import time
import xml.etree.ElementTree as ET
import re
import socket
import ssl
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit, urldefrag
from urllib.robotparser import RobotFileParser

from app.core.exceptions import ValidationError

USER_AGENT = "AIPSeoAuditor/1.0 (+public-page-technical-audit)"
MAX_HTML_BYTES = 1_000_000
MAX_PAGES = 15
MAX_REDIRECTS = 3


def validate_target(raw: str) -> str:
    """Reject userinfo, non-web schemes, restricted hosts, ports and URLs."""
    if not isinstance(raw, str) or len(raw) > 2048 or any(c.isspace() for c in raw):
        raise ValidationError("Please provide a valid public website URL.")
    parts = urlsplit(raw)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValidationError("Only public HTTP and HTTPS URLs are supported.")
    try:
        host = parts.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        port = parts.port
    except (ValueError, UnicodeError) as exc:
        raise ValidationError("Invalid website hostname or port.") from exc
    if port is not None and port != (443 if parts.scheme.lower() == "https" else 80):
        raise ValidationError("Custom ports are not permitted.")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValidationError("Private or reserved IP addresses are not permitted.")
    except ValueError:
        pass  # Ordinary DNS name; validate resolved addresses before connecting.
    if host in {"localhost", "0", "0.0.0.0"} or host.endswith((".localhost", ".local", ".internal", ".test", ".invalid", ".example", ".onion")):
        raise ValidationError("The website must use a public hostname.")
    if not re.fullmatch(r"[a-z0-9.\-:]+", host) or ".." in host:
        raise ValidationError("Invalid website hostname.")
    if not host or ("." not in host and ":" not in host):
        raise ValidationError("The website must use a public hostname.")
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), host, path, parts.query, ""))


def public_addresses(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        ips = list(dict.fromkeys(info[4][0] for info in infos))
    except (socket.gaierror, OSError) as exc:
        raise ValidationError("Could not resolve website DNS.") from exc
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValidationError("Private, local, reserved or mixed DNS addresses are not permitted.")
    return ips


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, hostname: str, ip: str, **kwargs: Any):
        self.pinned_ip = ip
        super().__init__(hostname, **kwargs)
    def connect(self) -> None:
        self.sock = socket.create_connection((self.pinned_ip, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, hostname: str, ip: str, **kwargs: Any):
        self.pinned_ip = ip
        super().__init__(hostname, context=ssl.create_default_context(), **kwargs)
    def connect(self) -> None:
        self.sock = socket.create_connection((self.pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


@dataclass
class FetchResult:
    url: str
    status: int
    content_type: str
    body: str
    headers: dict[str, str] = field(default_factory=dict)
    response_ms: float | None = None


def _network_error_message(exc: Exception) -> str:
    """Safe diagnostics for users, without disclosing resolved addresses."""
    if isinstance(exc, ssl.SSLCertVerificationError):
        return "TLS certificate verification failed. Check the site's HTTPS certificate and clock."
    if isinstance(exc, ssl.SSLError):
        return "HTTPS handshake failed. Check the server's TLS configuration."
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "Connection timed out. Check server availability, DNS and firewall rules."
    if isinstance(exc, ConnectionRefusedError):
        return "Connection refused by the remote server. Check that port 80 or 443 is open."
    if isinstance(exc, (ConnectionResetError, BrokenPipeError, http.client.RemoteDisconnected)):
        return "The remote server closed the connection. Check firewall and anti-bot policies."
    if isinstance(exc, OSError):
        return "Network connection failed. Check DNS, IPv4/IPv6 connectivity, firewall and proxy settings."
    return "The remote server returned an invalid HTTP response."


def fetch_public_page(url: str, *, redirects: int = 0, allow_xml: bool = False, allow_text: bool = False) -> FetchResult:
    """Bounded public-page fetch, pinned to validated IPs with IPv4/IPv6 fallback."""
    url = validate_target(url)
    parts = urlsplit(url)
    hostname = parts.hostname or ""
    # Never retry on an unvalidated address: all addresses are public and pinned.
    validated = public_addresses(hostname)
    addresses = sorted(validated, key=lambda ip: 0 if ipaddress.ip_address(ip).version == 4 else 1)[:4]
    conn_cls = _PinnedHTTPS if parts.scheme == "https" else _PinnedHTTP
    path = urlunsplit(("", "", parts.path or "/", parts.query, ""))
    last_error: Exception | None = None
    for ip in addresses:
        conn = conn_cls(hostname, ip, port=443 if parts.scheme == "https" else 80, timeout=5)
        try:
            started = time.monotonic()
            conn.request("GET", path, headers={"Host": hostname, "User-Agent": USER_AGENT, "Accept": "text/html, text/plain;q=0.5", "Accept-Encoding": "identity", "Connection": "close"})
            response = conn.getresponse()
            status = response.status
            response_ms = round((time.monotonic() - started) * 1000, 1)
            headers = {k.lower(): v for k, v in response.getheaders()}
            if status in (301, 302, 303, 307, 308):
                if redirects >= MAX_REDIRECTS:
                    raise ValidationError("Website redirect limit exceeded.")
                location = headers.get("location", "")
                if not location:
                    raise ValidationError("Website returned a redirect without Location.")
                return fetch_public_page(validate_target(urljoin(url, location)), redirects=redirects + 1, allow_xml=allow_xml, allow_text=allow_text)
            if headers.get("content-length", "").isdigit() and int(headers["content-length"]) > MAX_HTML_BYTES:
                raise ValidationError("Page is larger than the scan limit.")
            content_type = headers.get("content-type", "").lower()
            accepted = ('text/html', 'application/xhtml+xml') + (('text/plain',) if allow_text else ()) + (('application/xml', 'text/xml') if allow_xml else ())
            if not any(t in content_type for t in accepted):
                raise ValidationError("Target did not return an HTML page.")
            body = response.read(MAX_HTML_BYTES + 1)
            if len(body) > MAX_HTML_BYTES:
                raise ValidationError("Page is larger than the scan limit.")
            encoding_match = re.search(r"charset\s*=\s*['\"]?([a-z0-9\-]+)", content_type)
            encoding = encoding_match.group(1) if encoding_match else "utf-8"
            try:
                text = body.decode(encoding, errors="replace")
            except LookupError:
                text = body.decode("utf-8", errors="replace")
            return FetchResult(url=url, status=status, content_type=content_type, body=text, headers=headers, response_ms=response_ms)
        except (OSError, ssl.SSLError, http.client.HTTPException, TimeoutError) as exc:
            last_error = exc
            continue
        finally:
            conn.close()
    raise ValidationError(_network_error_message(last_error or OSError("Unable to connect"))) from last_error


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.canonical = ""
        self.robots = ""
        self.viewport = False
        self.lang = ""
        self.h1: list[str] = []
        self.h2: list[str] = []
        self.visible_text: list[str] = []
        self._skip_depth = 0
        self._heading = None
        self.images = 0
        self.images_missing_alt = 0
        self.links: list[str] = []
        self._title = False
        self._h1 = False
        self.og_title = ""
        self.og_description = ""
        self.og_image = ""
        self.schema_types: list[str] = []
        self.jsonld_errors = 0
        self._jsonld = False
        self._jsonld_body = ""
        self.image_lazy = 0
        self.h3: list[str] = []
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "html": self.lang = (a.get("lang") or "").strip()
        if tag == "title": self._title = True
        if tag in ("script", "style", "svg", "noscript", "nav", "footer"):
            self._skip_depth += 1
        if tag == "h1": self._h1 = True; self.h1.append("")
        if tag == "h2": self.h2.append(""); self._heading = "h2"
        if tag == "h3": self.h3.append(""); self._heading = "h3"
        if tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self._jsonld = True
            self._jsonld_body = ""
        if tag == "meta":
            name = (a.get("name") or "").lower()
            prop = (a.get("property") or "").lower()
            if prop == "og:title": self.og_title = a.get("content") or ""
            if prop == "og:description": self.og_description = a.get("content") or ""
            if prop == "og:image": self.og_image = a.get("content") or ""
            if name == "description": self.description = a.get("content") or ""
            if name == "robots": self.robots = a.get("content") or ""
            if name == "viewport": self.viewport = True
        if tag == "link" and "canonical" in (a.get("rel") or "").lower().split(): self.canonical = a.get("href") or ""
        if tag == "img":
            self.images += 1
            if (a.get("loading") or "").lower() == "lazy": self.image_lazy += 1
            if a.get("alt") is None: self.images_missing_alt += 1
        if tag == "a" and a.get("href"): self.links.append(a["href"] or "")
    def handle_endtag(self, tag: str) -> None:
        if tag == "title": self._title = False
        if tag in ("script", "style", "svg", "noscript", "nav", "footer") and self._skip_depth:
            self._skip_depth -= 1
        if tag == "h1": self._h1 = False
        if tag in ("h2", "h3"): self._heading = None
        if tag == "script" and self._jsonld:
            try:
                obj = json.loads(self._jsonld_body[:100000])
                queue = obj if isinstance(obj, list) else [obj]
                for doc in queue:
                    if isinstance(doc, dict):
                        if isinstance(doc.get('@graph'), list): queue.extend(doc['@graph'][:30])
                        typ = doc.get('@type', '')
                        if isinstance(typ, list): self.schema_types.extend(str(t)[:80] for t in typ[:12])
                        elif typ: self.schema_types.append(str(typ)[:80])
            except (json.JSONDecodeError, ValueError, TypeError):
                self.jsonld_errors += 1
            self._jsonld = False
            self._jsonld_body = ''
    def handle_data(self, data: str) -> None:
        if self._title: self.title += data
        if self._h1 and self.h1: self.h1[-1] += data
        if self._heading == "h2" and self.h2: self.h2[-1] += data
        if self._heading == "h3" and self.h3: self.h3[-1] += data
        if self._jsonld and len(self._jsonld_body) < 100000: self._jsonld_body += data
        if not self._skip_depth and data.strip() and sum(map(len, self.visible_text)) < 140000:
            self.visible_text.append(data.strip())


def finding(rule: str, category: str, severity: str, title: str, description: str, recommendation: str, page_url: str, evidence: str = "") -> dict[str, str]:
    return dict(rule=rule, category=category, severity=severity, title=title, description=description, recommendation=recommendation, page_url=page_url, evidence=evidence[:500])


def analyze_html(page: FetchResult) -> tuple[list[dict[str, str]], PageParser]:
    parser = PageParser()
    parser.feed(page.body)
    url = page.url
    issues: list[dict[str, str]] = []
    def add(rule: str, category: str, severity: str, title: str, why: str, fix: str, evidence: str = "") -> None:
        issues.append(finding(rule, category, severity, title, why, fix, url, evidence))
    if page.status < 200 or page.status >= 300:
        add("http_error", "crawlability", "critical", f"HTTP {page.status} response", "This page returned an HTTP error status.", "Fix the URL or the server response so the page returns HTTP 200.", str(page.status))
    if not parser.title.strip():
        add("missing_title", "on_page", "high", "Missing page title", "Search engines rely on descriptive title elements.", "Add a unique, meaningful <title> for this page.")
    elif len(parser.title.strip()) > 65:
        add("long_title", "on_page", "low", "Long page title", "The title may be truncated in search results.", "Aim for a concise title around 50–60 characters.", parser.title.strip()[:100])
    if not parser.description.strip():
        add("missing_description", "on_page", "medium", "Missing meta description", "This page lacks a search result summary.", "Write a unique description summarizing the page (roughly 120–160 characters).")
    elif len(parser.description.strip()) > 165:
        add("long_description", "on_page", "low", "Long meta description", "The snippet may be truncated in search results.", "Tighten the description to a useful concise summary.", parser.description[:180])
    if len(parser.h1) == 0:
        add("missing_h1", "content", "medium", "Missing H1 heading", "The page has no primary heading.", "Add one clear H1 that reflects page intent.")
    elif len(parser.h1) > 1:
        add("multiple_h1", "content", "low", "Multiple H1 headings", "Multiple primary headings may weaken page hierarchy.", "Use a clear heading hierarchy with one main H1.", str(len(parser.h1)))
    if not parser.lang:
        add("missing_lang", "accessibility", "low", "Missing HTML language", "Screen readers and browsers need the document language.", "Add an appropriate lang attribute to the <html> element.")
    if not parser.viewport:
        add("missing_viewport", "mobile", "medium", "Missing viewport meta tag", "The page may not adapt correctly on mobile devices.", "Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">.")
    if parser.images_missing_alt:
        add("missing_image_alt", "accessibility", "medium", "Images missing alternative text", "Some image elements have no descriptive alt text.", "Add informative alt text to content images and alt=\"\" to decorative images.", f"{parser.images_missing_alt} of {parser.images} images")
    header_robots = page.headers.get('x-robots-tag', '')
    if 'noindex' in header_robots.lower():
        add('xrobots_noindex', 'crawlability', 'high', 'X-Robots-Tag blocks indexing',
            'The HTTP response instructs search engines not to index this page.',
            'Remove the noindex response header only if indexing is intended.', header_robots[:180])
    header_robots = page.headers.get('x-robots-tag', '')
    if 'noindex' in header_robots.lower():
        add('xrobots_noindex', 'crawlability', 'high', 'X-Robots-Tag blocks indexing',
            'The HTTP response instructs search engines not to index this page.',
            'Remove the noindex response header only if indexing is intended.', header_robots[:180])
    if "noindex" in parser.robots.lower():
        add("noindex", "crawlability", "high", "Page requests no indexing", "The robots meta tag contains noindex.", "Remove noindex if this page should be indexed.", parser.robots)
    if not parser.canonical:
        add("missing_canonical", "technical", "low", "Missing canonical URL", "No canonical hint was found for this page.", "Add a self-referencing canonical link where appropriate.")
    elif urlsplit(urljoin(url, parser.canonical)).hostname != urlsplit(url).hostname:
        add("external_canonical", "technical", "medium", "Canonical points to another host", "The canonical URL is on another host.", "Confirm this cross-domain canonical is intentional.", parser.canonical)
    if parser.jsonld_errors:
        add('invalid_jsonld', 'structured_data', 'medium', 'Invalid JSON-LD syntax',
            'At least one structured-data JSON block cannot be parsed.',
            'Validate JSON-LD syntax and eligible schema types using a rich-results testing tool.',
            str(parser.jsonld_errors) + ' invalid JSON-LD block(s)')
    if not parser.og_title or not parser.og_image:
        add('social_preview', 'social', 'low', 'Incomplete social sharing metadata',
            'Open Graph title or image is missing; share previews may be inconsistent.',
            'Provide og:title and og:image with an appropriate publicly accessible image.')
    if page.response_ms is not None and page.response_ms > 1100:
        add('slow_response', 'performance', 'medium', 'Slow initial HTTP response',
            'The time until the first response headers was above 1.1 seconds in this single observation.',
            'Profile server response timing from several regions; investigate caching and backend latency.',
            f'{page.response_ms} ms; one crawler sample, not Core Web Vitals')
    if urlsplit(url).scheme == 'https' and not page.headers.get('strict-transport-security'):
        add('missing_hsts', 'security', 'low', 'HSTS header not detected',
            'No HTTP Strict-Transport-Security response header was observed.',
            'Consider an HSTS policy after confirming HTTPS readiness across subdomains.')
    if urlsplit(url).scheme == "http":
        add("insecure_http", "security", "high", "Page is not using HTTPS", "Content is delivered over unencrypted HTTP.", "Enable HTTPS and redirect HTTP to HTTPS.")
    return issues, parser


# Local keyword extraction provides ON-PAGE evidence. No search-volume, SERP, or
# competitor estimates: these require Search Console or a third-party provider.
_STOPWORDS = set(('the and for are with from this that your have will into about these those how why who can you our their when was were has not but they this all more than its page site website read home contact service services products product learn click here on at by of or to in is it as be a an we us which may using use content them you ve more also over under guide best new one two three about most each between next get find'.split()))
_STOPWORDS |= set('و در به از که این آن برای با است را های ها یک می شود شده تا خود بر یا اما اگر چه هر همه نیز مثل درباره روی شما ما آنها او من شماست طور مورد پس قبل بعد هنگام بسیار طور دیگر اطلاعات سایت صفحه محصول محصولات خرید قیمت خدمات درباره تماس خانه همان بین نیز درون'.split())
_STOPWORDS |= set('في من على إلى عن هذا هذه ذلك التي الذي مع هو هي هم كان كما لقد بعد قبل عند كل أو ثم هنا هناك المزيد الموقع الموقعين الصفحة المنتجات الخدمات الأسعار اقرأ'.split())
_TOKEN = re.compile(r"[^\W\d_]{3,}", flags=re.UNICODE)

def tokens(text: str) -> list[str]:
    text = text.lower().replace('ي', 'ی').replace('ك', 'ک').replace('ـ', '')
    return [token for token in _TOKEN.findall(text) if token not in _STOPWORDS and len(token) <= 32]

def content_summary(parser: PageParser, page_url: str) -> dict[str, Any]:
    visible = ' '.join(parser.visible_text)
    words = tokens(visible)
    counts = Counter(words)
    title_tokens = set(tokens(parser.title + ' ' + ' '.join(parser.h1)))
    # Prioritize topics used in headings but explicitly report observed frequency.
    unigrams = [(term, count, count + (5 if term in title_tokens else 0)) for term, count in counts.items() if count >= 2]
    bigrams = Counter(' '.join(pair) for pair in zip(words, words[1:]) if pair[0] != pair[1])
    phrases = [(term, count, count * 1.3 + (5 if any(x in title_tokens for x in term.split()) else 0))
               for term, count in bigrams.items() if count >= 2]
    ranked = sorted(unigrams + phrases, key=lambda x: (-x[2], -x[1], x[0]))[:12]
    parsed_url = urlsplit(page_url)
    links = [urljoin(page_url, link) for link in parser.links if link.startswith(('/', 'http://', 'https://'))]
    return {
        'url': page_url, 'title': parser.title.strip()[:200],
        'description': parser.description.strip()[:300], 'h1': [h.strip()[:160] for h in parser.h1],
        'h2': [h.strip()[:160] for h in parser.h2[:12]],
        'h3': [h.strip()[:160] for h in parser.h3[:12]],
        'word_count': len(words), 'visible_characters': len(visible),
        'meta_robots': parser.robots, 'canonical': parser.canonical,
        'response_ms': None, 'schema_types': parser.schema_types[:12],
        'og_title': parser.og_title[:160], 'og_image': parser.og_image[:250],
        'images': parser.images, 'images_missing_alt': parser.images_missing_alt,
        'internal_links': sum(urlsplit(u).hostname == parsed_url.hostname for u in links),
        'external_links': sum(urlsplit(u).hostname != parsed_url.hostname for u in links),
        'internal_link_targets': [u[:600] for u in links if urlsplit(u).hostname == parsed_url.hostname][:80],
        'keywords': [{'term': term, 'occurrences': count, 'in_heading': any(part in title_tokens for part in term.split())}
                     for term, count, _ in ranked],
    }

def content_recommendations(pages: list[dict[str, Any]]) -> list[dict[str, str]]:
    actions = []
    for page in pages:
        if page['word_count'] < 160:
            actions.append({'priority': 'high', 'page': page['url'],
                'title': 'Review shallow page content',
                'reason': f"Only {page['word_count']} visible substantive words were extracted (menus/footers excluded).",
                'action': 'Check whether this page satisfies visitor intent; add original explanations, examples and answers if needed.'})
        if not page['keywords']:
            actions.append({'priority': 'medium', 'page': page['url'],
                'title': 'Clarify page topic', 'reason': 'Few repeated meaningful terms were found in the visible text.',
                'action': 'Use a descriptive title, a clear main heading and genuinely helpful topical content.'})
    title_groups = {}
    for page in pages:
        if page['title']:
            title_groups.setdefault(page['title'].casefold(), []).append(page['url'])
    for urls in title_groups.values():
        if len(urls) > 1:
            actions.append({'priority': 'high', 'page': urls[0], 'title': 'Duplicate page titles',
                'reason': f"The same title was found on {len(urls)} scanned pages.",
                'action': 'Write distinct, intent-focused titles for these pages: ' + ', '.join(urls[:3])})
    # Cross-page overlap is an editorial review signal, not proof of
    # keyword cannibalization (that requires rankings + landing page data).
    for i, a in enumerate(pages):
        for b in pages[i+1:]:
            ta, tb = set(tokens(a.get('title', '') + ' ' + ' '.join(a.get('h1', [])))), set(tokens(b.get('title', '') + ' ' + ' '.join(b.get('h1', []))))
            if len(ta) >= 2 and len(tb) >= 2:
                overlap = len(ta & tb) / len(ta | tb)
                if overlap >= 0.8:
                    actions.append({'priority': 'medium', 'page': a['url'],
                        'title': 'Potentially overlapping search intent',
                        'reason': f'Headline topic overlap {round(overlap*100)}% between {a["url"]} and {b["url"]}.',
                        'action': 'Check whether the pages satisfy distinct user intents before changing URLs or canonicals.'})
    return actions[:30]


def run_audit(site_url: str, max_pages: int = MAX_PAGES) -> dict[str, Any]:
    """Perform a bounded same-host HTML audit; never invent unavailable metrics."""
    site_url = validate_target(site_url)
    max_pages = max(1, min(max_pages, MAX_PAGES))
    root_host = urlsplit(site_url).hostname
    base = f"{urlsplit(site_url).scheme}://{root_host}"
    robots = RobotFileParser()
    robots_status = "unavailable"
    sitemap_urls: list[str] = []
    sitemap_status = "not_checked"
    try:
        robots_response = fetch_public_page(base + "/robots.txt", allow_text=True)
        robots_status = str(robots_response.status)
        if robots_response.status in (401, 403):
            raise ValidationError("The website robots.txt forbids automated access.")
        if robots_response.status == 200:
            robots.parse(robots_response.body.splitlines())
        elif robots_response.status in (404, 410):
            robots.allow_all = True
        else:
            raise ValidationError(f'robots.txt returned HTTP {robots_response.status}; automated access is uncertain.')
    except ValidationError as exc:
        # Fail closed on uncertain robots access. A crawler should not scan a
        # website when it cannot determine whether crawling is permitted.
        raise ValidationError('robots.txt could not be verified; audit halted: ' + str(exc)[:150]) from exc
    if not robots.can_fetch(USER_AGENT, site_url):
        raise ValidationError('No crawlable public HTML pages found (check robots.txt).')
    # Same-host sitemap discovery; XML is parsed with stdlib ElementTree (no
    # fetching external entity references). Robots.txt sitemap may be off-site:
    # do not follow it. The sitemap is advisory, never an indexing guarantee.
    try:
        sm = fetch_public_page(base + '/sitemap.xml', allow_xml=True)
        sitemap_status = str(sm.status)
        if sm.status == 200 and ('xml' in sm.content_type or sm.body.lstrip().startswith('<?xml')):
            root = ET.fromstring(sm.body[:MAX_HTML_BYTES])
            for item in root.iter():
                if item.tag.rsplit('}', 1)[-1] == 'loc' and item.text and len(sitemap_urls) < 80:
                    target = item.text.strip()
                    try:
                        safe = validate_target(target)
                        if urlsplit(safe).hostname == root_host and safe not in sitemap_urls:
                            sitemap_urls.append(safe)
                    except ValidationError:
                        continue
    except (ValidationError, ET.ParseError):
        sitemap_status = 'unavailable or invalid'
    queue = deque([site_url])
    seen: set[str] = set()
    issues: list[dict[str, str]] = []
    page_summaries: list[dict[str, Any]] = []
    successful_pages = 0
    failed_pages = 0
    content_pages: list[dict[str, Any]] = []
    while queue and len(seen) < max_pages:
        candidate = queue.popleft()
        normalized = urldefrag(candidate)[0]
        if normalized in seen: continue
        if urlsplit(normalized).hostname != root_host: continue
        if not robots.can_fetch(USER_AGENT, normalized): continue
        seen.add(normalized)
        try:
            page = fetch_public_page(normalized)
            if urlsplit(page.url).hostname != root_host:
                issues.append(finding('redirect_other_host', 'crawlability', 'high',
                    'Redirect leaves the configured hostname',
                    'The requested page redirected to a different hostname which is outside this scan scope.',
                    'Register the canonical destination hostname as a separate website to audit it.',
                    normalized, page.url[:500]))
                page_summaries.append({'url': normalized, 'status': 'error', 'title':'', 'issues':1})
                failed_pages += 1
                continue
            # A server-side 4xx/5xx response is evidence of a failed fetch, not
            # a valid HTML document on which to calculate the site's SEO score.
            if page.status < 200 or page.status >= 300:
                issues.append(finding("http_error", "crawlability", "critical", f"HTTP {page.status} response", "The server returned an error response.", "Resolve the HTTP error and run the audit again.", page.url, str(page.status)))
                page_summaries.append({"url": page.url, "status": page.status, "title": "", "issues": 1})
                failed_pages += 1
                continue
            page_issues, parsed = analyze_html(page)
            summary_page = content_summary(parsed, page.url)
            summary_page['response_ms'] = page.response_ms
            content_pages.append(summary_page)
            successful_pages += 1
            issues.extend(page_issues)
            page_summaries.append({"url": page.url, "status": page.status, "title": parsed.title.strip()[:120], "issues": len(page_issues)})
            if not queue and sitemap_urls:
                for candidate_url in sitemap_urls[:max_pages*2]:
                    if candidate_url not in seen and candidate_url not in queue: queue.append(candidate_url)
            for link in parsed.links[:80]:
                if link.startswith(("mailto:", "tel:", "javascript:", "data:")): continue
                target = urldefrag(urljoin(page.url, link))[0]
                parts = urlsplit(target)
                if parts.hostname == root_host and parts.scheme in ("http", "https") and target not in seen and target not in queue:
                    try: queue.append(validate_target(target))
                    except ValidationError: pass
        except ValidationError as exc:
            issues.append(finding("fetch_failed", "crawlability", "high", "Page could not be fetched", "The audit could not retrieve this page.", "Check HTTP status, DNS, TLS and accessibility.", normalized, str(exc)))
            page_summaries.append({"url": normalized, "status": "error", "title": "", "issues": 1})
            failed_pages += 1
    if not page_summaries:
        raise ValidationError("No crawlable public HTML pages found (check robots.txt).")
    # Internal links found on analyzed pages that returned an HTTP error during
    # this same audit are evidence-backed. Unfetched links are NOT labelled broken.
    broken_urls = {p['url'] for p in page_summaries if isinstance(p['status'], int) and p['status'] >= 400}
    if broken_urls:
        for page in content_pages:
            if page['url'] in broken_urls: continue
            # Link inventory is bounded separately below; no extra external fetches.
            page['observed_broken_target_count'] = sum(target in broken_urls for target in page.get('internal_link_targets', []))
    for page in content_pages:
        broken = [target for target in page.get('internal_link_targets', []) if target in broken_urls]
        if broken:
            issues.append(finding('broken_internal_links', 'crawlability', 'high',
                'Verified internal link targets return HTTP errors',
                f'{len(broken)} internal link(s) point to error responses observed during this limited scan.',
                'Repair or redirect the failing internal URL(s), then rescan.', page['url'],
                '; '.join(broken[:2])))
    content_actions = content_recommendations(content_pages)
    site_terms = Counter()
    for page in content_pages:
        for entry in page["keywords"]:
            site_terms[entry["term"]] += entry["occurrences"]
    site_keywords = [{"term": term, "occurrences_on_scanned_pages": count} for term, count in site_terms.most_common(18)]
    severity_counts = Counter(item["severity"] for item in issues)
    # Connectivity failures are diagnostics, not evidence of poor on-page SEO.
    scored_issues = [item for item in issues if item['category'] in
                     {'crawlability', 'on_page', 'content', 'technical', 'mobile', 'structured_data'}
                     and item['rule'] not in {'fetch_failed', 'http_error'}]
    penalty = sum({"critical": 22, "high": 12, "medium": 6, "low": 2}[item["severity"]] for item in scored_issues)
    score = max(0, round(100 - penalty / successful_pages)) if successful_pages else 0
    scan_status = "failed" if not successful_pages else "partial" if failed_pages else "completed"
    return {
        "score": score, "status": scan_status, "pages_scanned": successful_pages,
        "issues_count": len(issues),
        "summary": {
            "severity_counts": dict(severity_counts), "pages": page_summaries,
            "successful_pages": successful_pages, "failed_pages": failed_pages,
            "attempted_pages": len(page_summaries), "status": scan_status,
            "crawl_discovery": {"robots_status": robots_status, "sitemap_status": sitemap_status, "sitemap_urls_observed": len(sitemap_urls)},
            "content_analysis": {"pages": content_pages, "keywords": site_keywords,
                                 "recommendations": content_actions, "scope": "Observed terms on fetched pages; not keyword search demand, rankings or competitor research."},
            "methodology": "Heuristic SEO score based on supported crawlability, metadata and content checks for fetched HTML only. Social/security checks are reported separately (not scored). No Google rankings, backlinks, rendered JavaScript, Core Web Vitals or search-demand estimates."
        }, "findings": issues
    }
