"""One JSON-over-HTTP call with retries. Stdlib only; never puts the API key in an error.

Copy of reviews_job/httpjson.py: the dashboard image builds from dashboard/ only and cannot import reviews_job.
"""
import json
import time
import urllib.error
import urllib.request

RETRY_STATUS = (429, 500, 502, 503, 504)


def request_json(method, url, headers, body=None, secret=None, attempts=3, timeout=20):
    """Return (parsed_response, None) or (None, error_text).

    Retries 429/5xx and network errors with 1 s, 2 s backoff. `secret` is scrubbed from
    any error text, so callers can store or log it.
    """
    data = json.dumps(body).encode() if body is not None else None
    hdrs = dict(headers)
    if body is not None:
        hdrs["Content-Type"] = "application/json"
    error = "no attempt made"
    for attempt in range(attempts):
        req = urllib.request.Request(url, data, hdrs, method=method)
        retry = True
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode() or "{}"), None
        except urllib.error.HTTPError as e:
            text = " ".join(e.read().decode(errors="replace").split())
            error = f"HTTP {e.code}: {text[:300]}"
            retry = e.code in RETRY_STATUS
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            error = f"{type(e).__name__}: {e}"
        except ValueError as e:
            error = f"bad JSON in response: {e}"
            retry = False
        if secret:
            error = error.replace(secret, "***")
        if not retry:
            break
        if attempt < attempts - 1:
            time.sleep(2 ** attempt)
    return None, error
