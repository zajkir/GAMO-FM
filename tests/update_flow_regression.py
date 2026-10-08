from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

import updater

source = (root / "updater.py").read_text(encoding="utf-8")
launcher_source = (root / "launcher.py").read_text(encoding="utf-8")
version = json.loads((root / "version.json").read_text(encoding="utf-8"))["version"]

assert "def download_launcher_update(" in source
assert "def can_self_update_install_dir(" in source
assert "def launch_launcher_self_update(" in source
assert "def run_launcher_self_update_helper(" in source
assert "def _replace_launcher_targets(" in source
assert "--gamo-update-helper" in launcher_source
assert "download_launcher_update" in launcher_source
assert "launch_launcher_self_update" in launcher_source
assert "Launcher sa bezpečne vymení, overí a automaticky znovu spustí." in launcher_source
assert "Installer fallback handoff" in launcher_source
assert "consume_update_result" in launcher_source

# Result persistence survives process handoff and is consumed only once.
with tempfile.TemporaryDirectory() as tmp:
    old = os.environ.get("LOCALAPPDATA")
    os.environ["LOCALAPPDATA"] = tmp
    try:
        result_path = updater.update_result_path()
        result_path.write_text(json.dumps({
            "status": "success",
            "message": "OK",
            "exit_code": 0,
            "version": version,
        }), encoding="utf-8")
        result = updater.consume_update_result()
        assert result["status"] == "success"
        assert result["version"] == version
        assert not result_path.exists()
        assert updater.consume_update_result() is None

        # Cross-platform regression for the actual file replacement/rollback core.
        payload = Path(tmp) / "new-launcher.exe"
        canonical = Path(tmp) / "install" / "GAMO_Launcher.exe"
        alias = Path(tmp) / "install" / "GAMO_FM.exe"
        canonical.parent.mkdir(parents=True)
        payload.write_bytes(b"NEW-GAMO-LAUNCHER")
        canonical.write_bytes(b"OLD-CANONICAL")
        alias.write_bytes(b"OLD-ALIAS")
        expected = hashlib.sha256(payload.read_bytes()).hexdigest()

        replaced = updater._replace_launcher_targets(payload, [canonical, alias], expected)
        assert canonical in replaced and alias in replaced
        assert canonical.read_bytes() == b"NEW-GAMO-LAUNCHER"
        assert alias.read_bytes() == b"NEW-GAMO-LAUNCHER"
        assert updater.file_sha256(canonical) == expected
        assert updater.file_sha256(alias) == expected

        bad_payload = Path(tmp) / "bad-launcher.exe"
        bad_payload.write_bytes(b"CORRUPT")
        before = canonical.read_bytes()
        try:
            updater._replace_launcher_targets(bad_payload, [canonical], "0" * 64)
            raise AssertionError("Bad SHA-256 payload was accepted")
        except ValueError:
            pass
        assert canonical.read_bytes() == before

        # Windows CI validates that the self-update helper is a copied launcher
        # executable rather than a PowerShell-only handoff.
        if os.name == "nt":
            fake_exe = Path(tmp) / "installed" / "GAMO_Launcher.exe"
            fake_exe.parent.mkdir(parents=True)
            fake_exe.write_bytes(b"trusted-current-launcher")
            payload2 = Path(tmp) / "payload2.exe"
            payload2.write_bytes(b"next-launcher")
            expected2 = hashlib.sha256(payload2.read_bytes()).hexdigest()

            original_executable = updater.sys.executable
            original_frozen = getattr(updater.sys, "frozen", None)
            original_popen = updater.subprocess.Popen
            calls = []
            updater.sys.executable = str(fake_exe)
            updater.sys.frozen = True
            updater.subprocess.Popen = lambda args, **kwargs: calls.append((args, kwargs)) or object()
            try:
                assert updater.launch_launcher_self_update(
                    payload2,
                    process_id=43210,
                    install_dir=fake_exe.parent,
                    version=version,
                    expected_sha256=expected2,
                ) is True
            finally:
                updater.sys.executable = original_executable
                if original_frozen is None:
                    delattr(updater.sys, "frozen")
                else:
                    updater.sys.frozen = original_frozen
                updater.subprocess.Popen = original_popen

            assert len(calls) == 1
            args = calls[0][0]
            assert Path(args[0]).name.startswith("GAMO_Update_Helper_")
            assert args[1] == "--gamo-update-helper"
            job = json.loads(Path(args[2]).read_text(encoding="utf-8"))
            assert Path(job["relaunch"]).name == "GAMO_Launcher.exe"
            assert {Path(x).name for x in job["targets"]} == {"GAMO_Launcher.exe", "GAMO_FM.exe"}
            assert job["expected_sha256"] == expected2
            assert job["version"] == version
    finally:
        if old is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = old

print("Direct launcher self-update regression checks OK")
