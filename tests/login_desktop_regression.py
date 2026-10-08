from pathlib import Path

root = Path(__file__).resolve().parents[1]
login = (root / "templates" / "login.html").read_text(encoding="utf-8")
app = (root / "app.py").read_text(encoding="utf-8")

# Avoid WebView2's problematic email-field focus path in the desktop shell.
assert 'name="login_identifier"' in login
assert 'type="text" inputmode="email"' in login
assert 'autocomplete="username"' in login
assert 'autocapitalize="none"' in login
assert 'spellcheck="false"' in login
assert 'name="email"' not in login
assert "autofocus" not in login

# Keep standards-compliant password autofill without browser-specific hacks.
assert 'autocomplete="current-password"' in login
assert "request.form.get('login_identifier')" in app
assert "request.form.get('email')" in app  # backwards-compatible API/tests

print("Desktop login input regression checks OK")
