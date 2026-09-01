import hashlib
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "profiles" / "rtx5090-152k.env.example"
PATCH = ROOT / "patches" / "sglang-bounded-dflash.patch"
BUILD = ROOT / "scripts" / "build_bounded_image.sh"
SERVER = ROOT / "scripts" / "server.sh"
SETUP = ROOT / "scripts" / "setup_profile.sh"
RUNTIME = ROOT / "scripts" / "setup_runtime.sh"
PREFLIGHT = ROOT / "scripts" / "preflight.sh"
BENCHMARK = ROOT / "scripts" / "benchmark.py"
INSTALLER = ROOT / "windows" / "Install-Desktop-Launchers.ps1"
LAN_HELPER = ROOT / "windows" / "Enable-Qwen-LAN.ps1"
WINDOWS_START = ROOT / "windows" / "Start-Qwen-Max.cmd"


class ContractTests(unittest.TestCase):
    def test_lan_helper_and_launcher_are_private_subnet_scoped(self):
        helper = LAN_HELPER.read_text(encoding="utf-8")
        launcher = WINDOWS_START.read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for value in (
            "function Get-WslIPv4",
            "function Get-WindowsLanIPv4",
            "QwenSGLangLAN1234",
            "ProgramData",
            "LocalSubnet",
            "Private",
            "interface portproxy",
            "Start-Process",
            "-Verb RunAs",
            "-Wait",
        ):
            self.assertIn(value, helper)
        self.assertLess(launcher.index("Enable-Qwen-LAN.ps1"), launcher.index("keepalive.sh"))
        for value in ("-Distro", '"%DISTRO%"', "-Port", "1234"):
            self.assertIn(value, launcher)
        for value in ("LAN", "LocalSubnet", "Private", "unauthenticated"):
            self.assertIn(value, readme)
        self.assertNotIn("-Profile Any", helper)
        self.assertNotIn("-RemoteAddress Any", helper)

    def test_profile_has_pinned_qualified_values(self):
        source = PROFILE.read_text(encoding="utf-8")
        for value in (
            "TARGET_REVISION=e60a41d4574ea73fe02acfd5ca6b61dc0b566545",
            "DRAFT_REVISION=50307d4c4cde6860d4eee73e2547cd786fe8e8a4",
            "MAX_TOTAL_TOKENS=155648", "MEM_FRACTION_STATIC=0.93",
            "DFLASH_BLOCK_SIZE=9", "DFLASH_WINDOW_SIZE=16384",
            "CHUNKED_PREFILL_SIZE=1024", "KV_CACHE_DTYPE=fp8_e4m3",
            "DISABLE_RADIX_CACHE=1", "DISABLE_PREFILL_CUDA_GRAPH=1",
            "MAX_RUNNING_REQUESTS=1", "RANDOM_SEED=42", "PORT=1234",
        ):
            self.assertIn(value, source)

    def test_patch_is_exact_pinned_python_diff(self):
        source = PATCH.read_text(encoding="utf-8")
        self.assertEqual(
            hashlib.sha256(PATCH.read_bytes()).hexdigest(),
            "d080d3e087f56c9cfb338f9a3302fde70baab26857a9c7df17b4987ab8187d53",
        )
        self.assertIn("python/sglang/srt/speculative/dflash_bounded_cache.py", source)
        self.assertNotIn("\n--- a/docs/", source)
        self.assertNotIn("PATCH_COMMIT=", BUILD.read_text(encoding="utf-8"))

    def test_bounded_builder_has_pinned_base_and_provenance_checks(self):
        source = BUILD.read_text(encoding="utf-8") + (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
        for value in (
            "a1fe4e30a983b04bbb74099dfc71bc7148c5c577",
            "43816c14aaaf6a4d09b6d19e6bac9802774b23c43298d70552e93fd4d202848a",
            "git apply --check", "io.qwen38.sglang.patch.sha256",
            "org.opencontainers.image.base.digest",
        ):
            self.assertIn(value, source)

    def test_portable_paths_and_token_forwarding_policy(self):
        tracked = subprocess.check_output(["git", "-C", str(ROOT), "ls-files"], text=True).splitlines()
        text = "\n".join(
            (ROOT / path).read_text(encoding="utf-8", errors="ignore")
            for path in tracked
            if not path.startswith(("tests/", ".github/", "ci/"))
        )
        for forbidden in ("C:\\Users\\Kyle", "/root/src/sglang-bounded-dflash", "sha256:c66b5"):
            self.assertNotIn(forbidden, text)
        self.assertIn("REPO_ROOT=$HOME/", PROFILE.read_text(encoding="utf-8"))
        self.assertIn("MODEL_ROOT=$HOME/models", PROFILE.read_text(encoding="utf-8"))
        self.assertIn("--env HF_TOKEN", SETUP.read_text(encoding="utf-8"))
        self.assertNotIn("HF_TOKEN=", SETUP.read_text(encoding="utf-8"))

    def test_required_launchers_and_lf_policy(self):
        for name in ("Start-Qwen-Max.cmd", "Stop-Qwen-Max.cmd", "Install-Desktop-Launchers.ps1"):
            self.assertTrue((ROOT / "windows" / name).is_file())
        installer = (ROOT / "windows" / "Install-Desktop-Launchers.ps1").read_text(encoding="utf-8")
        self.assertIn("$Distro", installer)
        self.assertIn("wslpath -a", installer)
        for launcher in (ROOT / "windows" / "Start-Qwen-Max.cmd", ROOT / "windows" / "Stop-Qwen-Max.cmd"):
            self.assertIn("wsl.exe -d", launcher.read_text(encoding="utf-8"))
        self.assertIn("*.sh text eol=lf", (ROOT / ".gitattributes").read_text(encoding="utf-8"))

    def test_installer_parses_and_generated_launchers_are_quoted(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertNotIn('\\"DISTRO=', source)
        for value in ("wsl\\$", "wsl\\.localhost", "Distro does not match", "set \"DISTRO=", "set \"QWEN_WSL_REPO="):
            self.assertIn(value, source)
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell:
            command = "& { param($p) $e=$null; [System.Management.Automation.Language.Parser]::ParseFile($p,[ref]$null,[ref]$e) | Out-Null; if($e.Count){$e | %% { $_.ToString() }; exit 1} }"
            result = subprocess.run([powershell, "-NoProfile", "-Command", command, str(INSTALLER)], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_installer_derives_both_unc_forms_and_rejects_wrong_distro(self):
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe") or shutil.which("powershell") or shutil.which("pwsh")
        if powershell is None:
            self.skipTest("PowerShell is unavailable on this host")
        script_path = str(INSTALLER)
        # Native PowerShell Core on Linux accepts POSIX paths directly. Only a
        # Windows PowerShell executable reached through WSL needs conversion.
        if os.name != "nt" and Path(powershell).name.lower().endswith(".exe"):
            script_path = subprocess.check_output(["wslpath", "-w", script_path], text=True).strip()
        command = (
            ". '{script}'; "
            "$a=Resolve-WslRepositoryPath -RepositoryWindowsPath '\\\\wsl$\\Ubuntu\\home\\qwen' -Distro Ubuntu; "
            "$b=Resolve-WslRepositoryPath -RepositoryWindowsPath '\\\\wsl.localhost\\Ubuntu\\home\\qwen' -Distro Ubuntu; "
            "if($a -ne '/home/qwen' -or $b -ne '/home/qwen'){{exit 1}}; "
            "try{{Resolve-WslRepositoryPath -RepositoryWindowsPath '\\\\wsl$\\Other\\home\\qwen' -Distro Ubuntu; exit 1}}catch{{exit 0}}"
        ).format(script=script_path.replace("'", "''"))
        result = subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_runtime_uses_signed_apt_and_does_not_forward_token(self):
        source = RUNTIME.read_text(encoding="utf-8")
        for value in ("download.docker.com/linux/ubuntu/gpg", "docker.list", "signed-by=", "docker-ce", "usermod -aG docker", "SUDO_USER"):
            self.assertIn(value, source)
        for forbidden in ("sudo -E", "get.docker.com", "/tmp/qwen38-get-docker.sh", "nvidia-driver-", "cuda-drivers"):
            self.assertNotIn(forbidden, source.lower())

    def test_profile_reconciles_pinned_snapshots_and_inventory(self):
        source = SETUP.read_text(encoding="utf-8")
        for value in ("snapshot_download", "revision='$revision'", ".qwen38-snapshot-revision-", "model.safetensors.index.json", "weight_map", "quarantine_snapshot"):
            self.assertIn(value, source)
        self.assertNotIn('[[ -s "$destination/config.json" ]] && return 0', source)

    def test_profile_quarantines_unsafe_snapshots_and_quotes_default_paths(self):
        source = SETUP.read_text(encoding="utf-8")
        for value in ("validate_repo_id", "realpath -m", "MODEL_ROOT itself", "quarantine_snapshot", "mv \"$destination\" \"$quarantine\"", "root-owned", "REPO_ROOT=%q"):
            self.assertIn(value, source)
        self.assertNotIn("rm -rf -- \"$destination\"", source)
        with tempfile.TemporaryDirectory(prefix="qwen profile ") as tmp:
            root = Path(tmp) / "repo with spaces"; root.mkdir()
            profile = Path(tmp) / "profile.env"
            result = subprocess.run(["bash", str(SETUP), "--write-profile-only"], text=True, capture_output=True, env=os.environ | {"REPO_ROOT": str(root), "QWEN_PROFILE": str(profile)}, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            parsed = subprocess.run(["bash", "-c", 'source "$1"; printf "%s" "$REPO_ROOT"', "--", str(profile)], text=True, capture_output=True, check=False)
            self.assertEqual(parsed.returncode, 0, parsed.stderr)
            self.assertEqual(parsed.stdout, str(root))

    def test_preflight_checks_wsl2_and_both_ext4_paths(self):
        source = PREFLIGHT.read_text(encoding="utf-8")
        for value in ("WSL_INTEROP", "WSL2", '"$DEPLOY_ROOT"', '"$MODEL_ROOT"', "must be on WSL ext4"):
            self.assertIn(value, source)

    def test_benchmark_discards_warmups_and_hashes_reasoning(self):
        source = BENCHMARK.read_text(encoding="utf-8")
        for value in ("--warmups", "reasoning_content", "index < args.warmups", "prompt-file"):
            self.assertIn(value, source)

    def test_docs_security_and_checkpoint_ignores(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("https://huggingface.co/Qwen/Qwen3.8-27B", readme)
        self.assertIn("https://huggingface.co/Qwen/Qwen3.8-27B", notice)
        self.assertIn("2.8% slower on prose and 22.5% slower on code", readme)
        for pattern in ("*.safetensors", "*.bin", "*.pt", "*.ckpt"):
            self.assertIn(pattern, ignored)

    def test_docs_scope_cold_start_gates_separately_from_short_medians(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        results = (ROOT / "benchmarks" / "RESULTS.md").read_text(encoding="utf-8")
        poster = (ROOT / "assets" / "qwen38-5090-performance-poster.svg").read_text(encoding="utf-8")
        for source in (readme, results):
            self.assertIn("one production cold-start gate", source)
            self.assertIn("second production cold-start repeat", source)
            self.assertIn("138.65", source)
            self.assertIn("138.34", source)
        self.assertIn("read -rsp", readme)
        self.assertIn("export HF_TOKEN", readme)
        self.assertNotIn("MEDIANS AFTER WARMUP", poster)
        self.assertIn("THROUGHPUT VARIES WITH PROMPT + DFLASH ACCEPTANCE", poster)

    def test_resolve_uses_required_server_flags_without_docker(self):
        values = dict(
            line.split("=", 1)
            for line in PROFILE.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")
        )
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "profile.env"
            profile.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")
            environment = os.environ | {"QWEN_PROFILE": str(profile)}
            result = subprocess.run(["bash", str(SERVER), "resolve"], text=True, capture_output=True, env=environment, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        for flag in (
            "--max-total-tokens 155648", "--speculative-dflash-bounded-cache",
            "--disable-radix-cache", "--disable-prefill-cuda-graph",
            "--weight-loader-drop-cache-after-load", "--random-seed 42",
            "--max-running-requests 1",
            "--host 127.0.0.1",
        ):
            self.assertIn(flag, result.stdout)


if __name__ == "__main__":
    unittest.main()
