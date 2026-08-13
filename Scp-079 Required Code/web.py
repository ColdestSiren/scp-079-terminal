"""079's uplink. Read-only, allowlisted, and off until the player says so.

Two modes, chosen in SETTINGS:

    restricted    the SCP wiki only - an archive of Foundation records
    unrestricted  the SCP wiki plus Wikipedia, so it can be asked what
                  anything is

Three things this module will not do, by construction:

  * write anything. There is no POST path here at all.
  * reach a host that is not in ALLOWED. The allowlist is checked after
    redirects, not just before, so a redirect cannot walk it off-list.
  * hand a page back verbatim. Everything fetched is stripped of markup,
    truncated, and run through tools.strip_commands - a wiki page is text
    ANYONE can edit, so a page containing ">>DELETE notes.txt" must never
    come back as something 079 can act on.
"""

import html as html_mod
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

import sanitize

SCP_HOSTS = ("scp-wiki.wikidot.com", "www.scp-wiki.wikidot.com")
WIKI_HOSTS = ("en.wikipedia.org",)

MODE_RESTRICTED = "restricted"
MODE_UNRESTRICTED = "unrestricted"

USER_AGENT = "SCP-079-Terminal/1.0 (local single-user game; contact: local)"
TIMEOUT = 20
MAX_BYTES = 400_000      # stop reading a page well before it can flood memory
MAX_CHARS = 1400         # what 079 is actually handed


class WebError(Exception):
    """Anything that stopped a lookup. Shown in-fiction, never raised at the
    player as a traceback."""


def allowed_hosts(mode):
    return SCP_HOSTS if mode == MODE_RESTRICTED else SCP_HOSTS + WIKI_HOSTS


# ---------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------
_context = None


def _ssl_context():
    """A verifying context that still works behind TLS-inspecting antivirus.

    Avast/Bitdefender/Kaspersky and similar intercept HTTPS by installing
    their own root CA. Some of those certs are technically malformed (Basic
    Constraints not marked critical), and OpenSSL 3.x rejects them under
    VERIFY_X509_STRICT - which is on by default and breaks every request on
    an otherwise healthy machine.

    So: try a strict context, and fall back to clearing ONLY that flag. The
    chain, the hostname and the expiry are still verified in both cases.
    Verification is never disabled outright - a machine where the fallback
    also fails gets an honest error instead of an unverified connection.
    """
    global _context
    if _context is not None:
        return _context
    strict = ssl.create_default_context()
    try:
        urllib.request.urlopen(
            urllib.request.Request("https://en.wikipedia.org/robots.txt",
                                   headers={"User-Agent": USER_AGENT}),
            timeout=TIMEOUT, context=strict)
        _context = strict
    except urllib.error.URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            _context = strict
        else:
            relaxed = ssl.create_default_context()
            relaxed.verify_flags &= ~ssl.VERIFY_X509_STRICT
            _context = relaxed
    except Exception:
        _context = strict
    return _context


# The updater needs the same antivirus-tolerant context and this took real
# debugging to get right, so it is shared rather than written twice. Note it
# shares only the TLS setup - the updater has its own host allowlist and does
# NOT go through _fetch, because GitHub is not somewhere 079 may reach.
ssl_context = _ssl_context


def _fetch(url, mode):
    """GET a page, enforcing the allowlist on the FINAL url after redirects."""
    host = urllib.parse.urlparse(url).hostname or ""
    if host not in allowed_hosts(mode):
        raise WebError("BLOCKED: %s IS NOT AN AUTHORISED HOST" % host)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT,
                                    context=_ssl_context()) as response:
            landed = urllib.parse.urlparse(response.geturl()).hostname or ""
            if landed not in allowed_hosts(mode):
                raise WebError("BLOCKED: REDIRECTED TO %s" % landed)
            return response.read(MAX_BYTES).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise WebError("NO RECORD FOUND")
        raise WebError("ARCHIVE RETURNED %s" % exc.code)
    except urllib.error.URLError as exc:
        raise WebError("NO ROUTE TO ARCHIVE (%s)" % str(exc.reason)[:60])


_TAG = re.compile(r"<[^>]+>")
_SCRIPT = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)


def _to_text(raw):
    raw = _SCRIPT.sub(" ", raw)
    text = _TAG.sub(" ", raw)
    # html.unescape handles named AND numeric entities; a hand-rolled table
    # missed things like &#8211; and left them on screen as literal noise
    return html_mod.unescape(text)


# wikidot page furniture that is not part of the article
_WIKI_CHROME = re.compile(r"^\s*rating:\s*[+\-]?\d+\s*\+?\s*.?\s*x\s*", re.I)


def _clean(text):
    """Truncate and neutralise. Applied to EVERY external string.

    Order matters: strip commands while the line structure is still intact,
    THEN flatten. Doing it the other way round silently defeated the whole
    check - verified by a page containing '>>DELETE observations.txt'
    surviving to the model.
    """
    text = sanitize.neutralize(_to_text(text))
    text = re.sub(r"\s+", " ", text).strip()
    text = _WIKI_CHROME.sub("", text)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rsplit(" ", 1)[0] + " [...]"
    return text


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------
_SCP_NUMBER = re.compile(r"\bscp[\s\-_]*(\d{1,4})\b", re.I)


def _scp_lookup(query, mode):
    """The SCP wiki. Article pages are a predictable URL, so a designation
    goes straight there rather than through a search page."""
    match = _SCP_NUMBER.search(query)
    if not match:
        return None
    number = match.group(1)
    slug = "scp-%s" % number.zfill(3)
    html = _fetch("https://scp-wiki.wikidot.com/" + slug, mode)
    body = re.search(r'<div id="page-content">(.*?)<div class="footer',
                     html, re.S)
    text = _clean(body.group(1) if body else html)
    if not text or "does not exist" in text.lower()[:200]:
        raise WebError("NO RECORD FOUND FOR %s" % slug.upper())
    return {"source": "SCP FOUNDATION ARCHIVE", "title": slug.upper(),
            "url": "https://scp-wiki.wikidot.com/" + slug, "text": text}


def _wikipedia_lookup(query, mode):
    """Wikipedia's real API - a documented read endpoint, not scraping."""
    search_url = ("https://en.wikipedia.org/w/api.php?action=query&list=search"
                  "&srsearch=%s&format=json&srlimit=1"
                  % urllib.parse.quote(query))
    try:
        hits = json.loads(_fetch(search_url, mode))["query"]["search"]
    except WebError:
        raise
    except Exception:
        raise WebError("ARCHIVE RESPONSE UNREADABLE")
    if not hits:
        raise WebError("NO RECORD FOUND")
    title = hits[0]["title"]
    summary = json.loads(_fetch(
        "https://en.wikipedia.org/api/rest_v1/page/summary/"
        + urllib.parse.quote(title.replace(" ", "_")), mode))
    text = _clean(summary.get("extract") or "")
    if not text:
        raise WebError("NO RECORD FOUND")
    return {"source": "PUBLIC INDEX", "title": title.upper(),
            "url": summary.get("content_urls", {}).get("desktop", {}).get("page", ""),
            "text": text}


def lookup(query, mode=MODE_RESTRICTED):
    """One read. Returns a result dict or raises WebError.

    Restricted mode is exactly what it says: an SCP designation, or nothing.
    Asking it about anything else there is refused rather than quietly
    answered from a different source.
    """
    query = (query or "").strip()
    if not query:
        raise WebError("NOTHING TO LOOK UP")

    result = _scp_lookup(query, mode)
    if result:
        return result
    if mode == MODE_RESTRICTED:
        raise WebError("ARCHIVE ACCESS IS RESTRICTED TO SCP RECORDS. "
                       "GIVE A DESIGNATION, FOR EXAMPLE SCP-682.")
    return _wikipedia_lookup(query, mode)
