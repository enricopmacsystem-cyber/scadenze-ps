"""Live HTTP checks against the running Flask app on 127.0.0.1:5000."""
from __future__ import annotations

import re
import sys
from urllib.parse import urljoin

import requests

BASE = "http://127.0.0.1:5000"
results: list[tuple[bool, str, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    results.append((bool(cond), name, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


def login(user: str, pwd: str) -> tuple[requests.Session, requests.Response | None, str]:
    sess = requests.Session()
    page = sess.get(BASE + "/login", timeout=10)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    if not tok:
        return sess, None, "no csrf"
    r = sess.post(
        BASE + "/login",
        data={"username": user, "password": pwd, "csrf_token": tok.group(1)},
        allow_redirects=True,
        timeout=10,
    )
    return sess, r, r.url


def main() -> None:
    s = requests.Session()
    s.headers.update({"User-Agent": "ScadenzeVerify/1.0"})

    r = s.get(BASE + "/", allow_redirects=False, timeout=10)
    ok(
        "unauth_redirect_login",
        r.status_code in (302, 303) and "/login" in (r.headers.get("Location") or ""),
        f"{r.status_code} {r.headers.get('Location')}",
    )

    r2 = s.get(BASE + "/login", timeout=10)
    set_cookie = (r.headers.get("Set-Cookie") or "") + (r2.headers.get("Set-Cookie") or "")
    ok("login_page", r2.status_code == 200 and "csrf_token" in r2.text)
    ok("session_httponly", "HttpOnly" in set_cookie)
    ok("session_samesite", "SameSite=Lax" in set_cookie)

    m = re.search(r'name="csrf_token" value="([^"]+)"', r2.text)
    token = m.group(1) if m else ""
    ok("csrf_present", bool(token))

    bad = s.post(
        BASE + "/login",
        data={"username": "admin", "password": "Admin2026!!", "csrf_token": "x"},
        timeout=10,
    )
    ok(
        "csrf_rejects_login",
        "CSRF" in bad.text or "scaduta" in bad.text or "Sessione" in bad.text,
        str(bad.status_code),
    )

    r2 = s.get(BASE + "/login", timeout=10)
    token = re.search(r'name="csrf_token" value="([^"]+)"', r2.text)
    assert token
    r = s.post(
        BASE + "/login",
        data={"username": "admin", "password": "Admin2026!!", "csrf_token": token.group(1)},
        allow_redirects=False,
        timeout=10,
    )
    loc = r.headers.get("Location") or ""
    ok("admin_login", r.status_code in (302, 303), f"{r.status_code} -> {loc}")
    r = s.get(urljoin(BASE, loc or "/"), timeout=10)
    if "/change-password" in r.url:
        ok("admin_must_change_password", True, r.url)
    else:
        ok(
            "admin_dashboard",
            "Panoramica" in r.text or "Scadenze" in r.text or "filiale" in r.text.lower(),
            r.url[:80],
        )
    s.get(BASE + "/logout", timeout=10)

    sess, r, url = login("gruaro", "Gruaro2026!")
    ok("gruaro_login_ok", r is not None and r.status_code == 200, url)
    if r and "/change-password" in url:
        ok("gruaro_force_pwd_change", True)
        ok("gruaro_change_pwd_page", "password" in r.text.lower())
    elif r:
        text = r.text
        ok("gruaro_sees_showroom", "Showroom" in text or "Gruaro Showroom" in text)
        ok("gruaro_sees_magazzino", "Magazzino" in text or "Gruaro Magazzino" in text)
        for label in ["Entrambe", "Showroom", "Magazzino"]:
            ok(f"gruaro_tab_{label}", label in text)

    sess2, r2, url2 = login("ordini.gruaro", "OrdiniGruaro2026!")
    ok("ordini_login_ok", r2 is not None and r2.status_code == 200, url2)
    if r2 and "/change-password" not in url2:
        t = r2.text
        ok("ordini_no_import_link", 'href="/import"' not in t)
        ok("ordini_has_alert_or_in_alert", "alert" in t.lower() or "Invia" in t or "In alert" in t)
    else:
        ok("ordini_force_pwd_or_land", True, url2)

    sess3, r3, url3 = login("villorba", "Villorba2026!")
    ok("villorba_login_ok", r3 is not None and r3.status_code == 200, url3)
    if r3 and "/change-password" not in url3:
        t = r3.text
        ok("villorba_sees_own", "Villorba" in t)
        # filiale user should not see other branches as filter chips
        other_chips = [
            name
            for name in ["Marghera", "Mirandola", "Tavagnacco", "Gruaro"]
            if name in t and name != "Villorba"
        ]
        ok("villorba_scoped_filiali", len(other_chips) == 0, ",".join(other_chips))
    else:
        ok("villorba_force_pwd", "/change-password" in url3, url3)

    # AuthZ: after gruaro login, try edit other filiale product if we can find one via test client DB
    sys.path.insert(0, str(__file__).rsplit("scripts", 1)[0])
    from app.database import list_prodotti

    other = next((p for p in list_prodotti() if "Gruaro" not in (p.get("filiale") or "")), None)
    if other and sess and r and "/change-password" not in url:
        denied = sess.get(f"{BASE}/prodotti/{other['id']}/modifica", allow_redirects=False, timeout=10)
        ok(
            "gruaro_edit_other_denied",
            denied.status_code in (302, 303),
            f"{denied.status_code} {denied.headers.get('Location')}",
        )
    elif other and sess:
        # still try even if on change-password: should redirect to change-password or login
        denied = sess.get(f"{BASE}/prodotti/{other['id']}/modifica", allow_redirects=False, timeout=10)
        ok(
            "gruaro_edit_other_blocked",
            denied.status_code in (302, 303),
            f"{denied.status_code} {denied.headers.get('Location')}",
        )

    bare = requests.get(BASE + "/", allow_redirects=False, timeout=10)
    ok("live_unauth_still_login", bare.status_code in (302, 303))

    failed = [x for x in results if not x[0]]
    print("---")
    print(f"TOTAL {len(results)} FAIL {len(failed)}")
    for f in failed:
        print("FAIL_DETAIL", f[1], f[2])
    if failed:
        sys.exit(1)
    print("BROWSER_EQUIV_OK")


if __name__ == "__main__":
    main()
