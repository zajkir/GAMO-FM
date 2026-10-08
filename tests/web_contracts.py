from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
css = (ROOT / "static" / "app.css").read_text(encoding="utf-8")
html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

# No raw database terminology may leak into customer-facing forms.
combined = (js + "\n" + html).lower()
assert "asset db id" not in combined
assert "building db id" not in combined
assert "floor db id" not in combined

# Destructive actions must stay inside the GAMO confirmation UI.
assert "window.confirm(" not in js
assert 'id="confirmModal"' in html
assert 'id="confirmImpact"' in html
assert 'id="confirmExecuteButton"' in html
assert "/api/delete-impact/" in js
assert "_confirm" in js

# Privacy/MFA must be navigable without knowing a hidden URL.
assert 'href="/account/mfa"' in html
assert "Spravovať MFA" in html or "MFA" in html

# Ticket chat must incrementally poll only new messages and keep unread state.
assert "/messages?after=" in js
assert "setInterval(refreshTicketMessages" in js
assert "ticketUnreadMarker" in js
assert "ticketPollInterval" in js

# Digital Twin uses the cleaned V2 namespace and key interaction controls.
for token in ("dt2-stage", "dt2-floor", "dt2FocusButton", "dt2TechButton"):
    assert token in html or token in css or token in js

# Web admin must display the actual platform version rather than a stale fixed build.
assert "DESKTOP BUILD" not in html
assert "{{app_version}}" in html

# Core commercial FM additions are represented in the customer UI.
for token in ("Asset Tag / QR", "Dátum inštalácie", "Záruka do", "Riešenie / vykonané opatrenie"):
    assert token in js

print("GAMO web contracts OK")
