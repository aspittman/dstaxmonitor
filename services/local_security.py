"""Loopback-only browser request checks, separate from financial calculations."""
from urllib.parse import urlsplit

LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1'}


def local_origin_matches(origin, request_url):
    """Compare local origins by scheme and effective port, not raw URL spelling.

    Localhost aliases address the same trusted local service. CSRF validation is
    still required independently; different ports/schemes and opaque origins fail.
    """
    try:
        candidate = urlsplit(origin)
        expected = urlsplit(request_url)
        if candidate.scheme not in {'http', 'https'} or candidate.hostname not in LOCAL_HOSTS:
            return False
        if expected.hostname not in LOCAL_HOSTS:
            return False
        if candidate.username is not None or candidate.password is not None:
            return False
        if candidate.path not in {'', '/'} or candidate.query or candidate.fragment:
            return False
        def port(value):
            return value.port if value.port is not None else (443 if value.scheme == 'https' else 80)
        return candidate.scheme == expected.scheme and port(candidate) == port(expected)
    except (ValueError, TypeError):
        return False
