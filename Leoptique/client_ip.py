def get_client_ip(request):
    """Real client IP, for rate limiting.

    nginx *appends* the address it actually saw to any X-Forwarded-For the
    client sent ("<whatever the client claimed>, <real address>"), so the
    FIRST entry is attacker-controlled: rotating it gave every request its
    own rate-limit bucket (verified against production). The LAST entry is
    the one our own proxy added, so that's the one to trust. This assumes
    exactly one proxy (nginx) in front of Django; if a CDN is ever put in
    front, this needs revisiting. Falls back to REMOTE_ADDR when there is no
    header (direct access, local dev).

    Behind nginx REMOTE_ADDR is the proxy's own address for every visitor,
    so a limiter keyed on it alone makes all customers share one bucket.
    """
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[-1].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')
