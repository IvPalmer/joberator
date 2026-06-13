"""Unit tests for the dashboard Basic Auth gate.

Imports kanban.py directly (the HTTP server only starts under __main__, so
import is side-effect-free apart from the venv check). Run with the mcp venv
python so the jobspy import at module load succeeds and does not re-exec:

    mcp/.venv/bin/python tests/test_auth.py
"""
import base64
import importlib.util
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "kanban", os.path.join(ROOT, "scripts", "kanban.py")
)
kanban = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kanban)


def basic(user, pw):
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


def run():
    vba = kanban.verify_basic_auth
    U, P = "owl", "s3cret-pass"

    # correct credentials
    assert vba(basic(U, P), U, P) is True, "valid creds should pass"
    # scheme is case-insensitive ("basic" / "Basic")
    assert vba(basic(U, P).replace("Basic", "basic"), U, P) is True, "lowercase scheme should pass"
    # password with a colon in it (partition on first colon only)
    assert vba(basic(U, "a:b:c"), U, "a:b:c") is True, "colon password should pass"
    # wrong password / user
    assert vba(basic(U, "nope"), U, P) is False, "wrong password should fail"
    assert vba(basic("eve", P), U, P) is False, "wrong user should fail"
    # missing / malformed headers
    assert vba("", U, P) is False, "empty header should fail"
    assert vba("Bearer xyz", U, P) is False, "non-Basic scheme should fail"
    assert vba("Basic @@not-base64@@", U, P) is False, "bad base64 should fail"
    assert vba("Basic " + base64.b64encode(b"nocolon").decode(), U, P) is False, \
        "no colon in decoded creds should fail"

    # public path is exempt from auth
    assert "/guia" in kanban.PUBLIC_PATHS, "/guia must be public"

    print("verify_basic_auth: OK")


def run_modes():
    m = kanban.auth_mode
    # password set -> enforce regardless of bind
    assert m("0.0.0.0", True, False) == "enforce"
    assert m("127.0.0.1", True, False) == "enforce"
    # exposed, no password, no override -> locked (fail closed, still boots)
    assert m("0.0.0.0", False, False) == "locked"
    # exposed, no password, explicit override -> open
    assert m("0.0.0.0", False, True) == "open"
    # loopback, no password -> open (local single-user)
    assert m("127.0.0.1", False, False) == "open"
    assert m("localhost", False, False) == "open"
    print("auth_mode: OK")


def _invoke(method, path, auth_header=None):
    """Drive Handler.do_* with mocked I/O (no socket, no server boot).

    Returns (status_code, body_bytes).
    """
    handler = kanban.Handler.__new__(kanban.Handler)
    handler.request_version = "HTTP/1.1"
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.path = path
    handler.command = method
    handler.client_address = ("127.0.0.1", 0)
    handler.headers = {"Authorization": auth_header} if auth_header else {}
    handler.rfile = io.BytesIO()
    handler.wfile = io.BytesIO()
    getattr(handler, "do_" + method)()
    raw = handler.wfile.getvalue()
    status = int(raw.split(b" ", 2)[1])
    body = raw.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in raw else b""
    return status, body


def run_routing():
    # Enable auth for the duration of these checks (enforce mode)
    kanban.AUTH_ENABLED = True
    kanban.AUTH_USER = "owl"
    kanban.AUTH_PASS = "s3cret-pass"
    kanban.HOST = "127.0.0.1"
    kanban.ALLOW_UNAUTHENTICATED = False
    good = basic("owl", "s3cret-pass")

    # public review page: no auth, serves the HTML file
    status, body = _invoke("GET", "/guia")
    assert status == 200, f"/guia should be 200, got {status}"
    assert b"joberator" in body.lower(), "/guia should serve the review page"

    # dashboard without creds: 401 challenge
    status, _ = _invoke("GET", "/")
    assert status == 401, f"/ without creds should be 401, got {status}"

    # api without creds: 401 (must not leak data)
    status, _ = _invoke("GET", "/api/jobs")
    assert status == 401, f"/api/jobs without creds should be 401, got {status}"

    # write endpoint without creds: 401
    status, _ = _invoke("DELETE", "/api/jobs/1")
    assert status == 401, f"DELETE without creds should be 401, got {status}"

    # dashboard with correct creds: serves the app HTML
    status, body = _invoke("GET", "/", auth_header=good)
    assert status == 200, f"/ with creds should be 200, got {status}"
    assert b"<!DOCTYPE html>" in body, "/ with creds should serve dashboard HTML"

    # wrong creds: 401
    status, _ = _invoke("GET", "/", auth_header=basic("owl", "wrong"))
    assert status == 401, f"/ with wrong creds should be 401, got {status}"

    # HEAD is gated like GET (no more 501): 401 unauth on dashboard, 200 on /guia
    status, _ = _invoke("HEAD", "/")
    assert status == 401, f"HEAD / unauth should be 401, got {status}"
    status, _ = _invoke("HEAD", "/guia")
    assert status == 200, f"HEAD /guia should be 200, got {status}"

    # locked mode: exposed bind, no password -> 503 for private, /guia still public
    kanban.AUTH_ENABLED = False
    kanban.AUTH_PASS = ""
    kanban.HOST = "0.0.0.0"
    kanban.ALLOW_UNAUTHENTICATED = False
    status, _ = _invoke("GET", "/")
    assert status == 503, f"locked / should be 503, got {status}"
    status, _ = _invoke("GET", "/api/jobs")
    assert status == 503, f"locked /api/jobs should be 503, got {status}"
    status, body = _invoke("GET", "/guia")
    assert status == 200 and b"joberator" in body.lower(), "/guia stays public when locked"
    # restore loopback defaults
    kanban.HOST = "127.0.0.1"
    kanban.AUTH_ENABLED = True

    print("routing + gate: OK")


if __name__ == "__main__":
    run()
    run_modes()
    run_routing()
    print("ALL AUTH TESTS PASSED")
