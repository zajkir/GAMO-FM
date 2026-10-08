from pathlib import Path
import json
import os
import tempfile
import updater

root = Path(__file__).resolve().parents[1]
source = (root / "updater.py").read_text(encoding="utf-8")
launcher_source = (root / "launcher.py").read_text(encoding="utf-8")

assert "def consume_update_result():" in source
assert "def launch_installer_after_process_exit(path, process_id=None, relaunch_path=None, version=''):" in source
assert "-Wait -PassThru" in source
assert "Start-Process -FilePath $Relaunch" in source
assert "Save-Result 'success'" in source
assert "Save-Result 'failed'" in source
assert "update_helper.log" in source
assert "Launcher sa zavrie, nainštaluje aktualizáciu a automaticky sa znovu spustí." in launcher_source
assert "consume_update_result" in launcher_source
assert "_show_previous_update_result" in launcher_source
assert "relaunch_path=relaunch" in launcher_source

# Result persistence must survive process handoff and be consumed exactly once.
with tempfile.TemporaryDirectory() as tmp:
    old = os.environ.get("LOCALAPPDATA")
    os.environ["LOCALAPPDATA"] = tmp
    try:
        result_path = updater.update_result_path()
        result_path.write_text(json.dumps({
            "status": "success",
            "message": "OK",
            "exit_code": 0,
            "version": "9.0.0.15",
        }), encoding="utf-8")
        result = updater.consume_update_result()
        assert result["status"] == "success"
        assert result["version"] == "9.0.0.15"
        assert not result_path.exists()
        assert updater.consume_update_result() is None

        # On Windows validate the detached helper command without executing PowerShell.
        if os.name == "nt":
            installer = Path(tmp) / "GAMO_FM_Setup_test.exe"
            relaunch = Path(tmp) / "GAMO_Launcher.exe"
            installer.write_bytes(b"verified-installer")
            relaunch.write_bytes(b"launcher")

            calls = []
            original_popen = updater.subprocess.Popen
            updater.subprocess.Popen = lambda args, **kwargs: calls.append((args, kwargs)) or object()
            try:
                assert updater.launch_installer_after_process_exit(
                    installer,
                    process_id=43210,
                    relaunch_path=relaunch,
                    version="9.0.0.15",
                ) is True
            finally:
                updater.subprocess.Popen = original_popen

            assert len(calls) == 1
            args = calls[0][0]
            assert args[0].lower().endswith("powershell.exe")
            assert "-ExecutionPolicy" in args and "Bypass" in args
            helper = Path(args[args.index("-File") + 1])
            helper_text = helper.read_text(encoding="utf-8")
            assert "Wait-Process -Id $LauncherPid" in helper_text
            assert "$setup = Start-Process -FilePath $Installer" in helper_text
            assert "-Wait -PassThru" in helper_text
            assert "Start-Process -FilePath $Relaunch" in helper_text
            assert str(relaunch) in args
            assert "9.0.0.15" in args
    finally:
        if old is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = old

print("Windows self-update relaunch regression checks OK")
