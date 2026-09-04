import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "profiles" / "rtx5090-152k.env.example"
NATIVE_MTP_PROFILE = ROOT / "profiles" / "rtx5090-native-mtp-nvfp4.env.example"
NATIVE_MTP_MODEL_CARD = ROOT / "model-cards" / "qwopus3.8-27b-flash-nvfp4-mtp.md"
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

    def test_lan_helper_branches_for_mirrored_and_nat_networking(self):
        helper = LAN_HELPER.read_text(encoding="utf-8")
        self.assertIn("$mirroredMode = $wslAddress -eq $lanAddress", helper)
        self.assertIn("if ($mirroredMode)", helper)
        self.assertIn("ProxyExpected", helper)
        self.assertIn("Mode = if ($mirroredMode) { 'Mirrored' } else { 'NAT' }", helper)
        self.assertIn("$addressesToRemove = @($lanAddress)", helper)
        self.assertIn("foreach ($address in $addressesToRemove) { Remove-QwenPortProxy -ListenAddress $address }", helper)
        self.assertIn("expected the current NAT mapping.", helper)
        self.assertIn("Port-proxy verification failed: no proxy expected in mirrored mode.", helper)

    def test_lan_helper_state_records_mode_and_proxy_diagnostics(self):
        helper = LAN_HELPER.read_text(encoding="utf-8")
        self.assertIn("Mode = if ($mirroredMode) { 'Mirrored' } else { 'NAT' }", helper)
        self.assertIn("ProxyExpected = $proxyExpected", helper)
        self.assertIn("ProxyListenAddress", helper)
        self.assertIn("ProxyConnectAddress", helper)

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

    def test_native_mtp_profile_publishes_the_qualified_runtime_contract(self):
        self.assertTrue(NATIVE_MTP_PROFILE.is_file())
        source = NATIVE_MTP_PROFILE.read_text(encoding="utf-8")
        for value in (
            "PROFILE=rtx5090-native-mtp-nvfp4",
            "CONTAINER_NAME=qwen38-sglang-native-mtp",
            "BOUNDED_IMAGE_REF=local/sglang:qwen38-bounded-dflash-a1fe4e30",
            "MODEL_ROOT=$HOME/models",
            "TARGET_REPO=Shiftedx/Qwopus3.8-27B-Flash-NVFP4-MTP",
            "TARGET_REVISION=e46dcfbe1aef581743509edb3a3c2c8934c3942d",
            "ENGINE=native_mtp",
            "SETUP_MODE=native_download",
            "CONTEXT_LENGTH=131072",
            "MAX_TOTAL_TOKENS=129241",
            "CHUNKED_PREFILL_SIZE=1024",
            "MAX_MAMBA_CACHE_SIZE=1",
            "MEM_FRACTION_STATIC=0.96",
            "MAX_RUNNING_REQUESTS=1",
            "RANDOM_SEED=42",
            "PORT=1234",
        ):
            self.assertIn(value, source)
        self.assertNotIn("SERVER_IMAGE_REF=", source)
        self.assertNotIn("c66b5add33e7a18992399a43b500a716ef28c44362a83c6e5b7d89d3dae48a9d", source)
        self.assertNotIn("Jackrong/Qwopus3.8-27B-Flash-NVFP4-MTP", source)
        self.assertNotIn("Shiftedx/Qwopus3.8-27B-Flash-NVFP4-MTP-RTX5090", source)

    def test_resolve_runs_native_mtp_without_dflash_or_language_only_flags(self):
        values = dict(
            line.split("=", 1)
            for line in NATIVE_MTP_PROFILE.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")
        )
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "profile.env"
            profile.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")
            result = subprocess.run(
                ["bash", str(SERVER), "resolve"], text=True, capture_output=True,
                env=os.environ | {"QWEN_PROFILE": str(profile)}, check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        for flag in (
            "--model-path /model", "--served-model-name qwopus3.8-27b-nvfp4-mtp",
            "--max-total-tokens 129241", "--context-length 131072",
            "--chunked-prefill-size 1024", "--max-mamba-cache-size 1",
            "--mem-fraction-static 0.96", "--max-running-requests 1",
            "--speculative-algorithm EAGLE", "--speculative-draft-model-path /model",
            "--speculative-num-steps 3", "--speculative-eagle-topk 1",
            "--speculative-num-draft-tokens 4", "--disable-radix-cache",
            "--disable-prefill-cuda-graph", "--random-seed 42", "--host 0.0.0.0",
            "--name qwen38-sglang-native-mtp", "-v /root/models/Shiftedx/Qwopus3.8-27B-Flash-NVFP4-MTP:/model:ro",
            "local/sglang:qwen38-bounded-dflash-a1fe4e30",
        ):
            self.assertIn(flag, result.stdout)
        for forbidden in (
            "--language-only", "--mm-feature-transport", "--speculative-dflash",
            "--speculative-draft-model-quantization", "/model_dflash", "--cpu-offload",
        ):
            self.assertNotIn(forbidden, result.stdout)

    def test_setup_can_seed_the_native_mtp_profile_without_changing_the_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "portable repo"; root.mkdir()
            profile = Path(tmp) / "native-mtp.env"
            result = subprocess.run(
                ["bash", str(SETUP), "--write-profile-only"], text=True, capture_output=True,
                env=os.environ | {
                    "REPO_ROOT": str(root), "QWEN_PROFILE": str(profile),
                    "QWEN_PROFILE_TEMPLATE": str(NATIVE_MTP_PROFILE),
                }, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            selected_engine = subprocess.run(
                ["bash", "-c", 'source "$1"; printf "%s" "$ENGINE"', "--", str(profile)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(selected_engine.returncode, 0, selected_engine.stderr)
            self.assertEqual(selected_engine.stdout, "native_mtp")

    def test_native_existing_setup_uses_bounded_image_provenance_not_a_local_image_id(self):
        source = SETUP.read_text(encoding="utf-8")
        self.assertIn('REPO_ROOT="$REPO_ROOT" BOUNDED_IMAGE_REF="$BOUNDED_IMAGE_REF" bash "$SCRIPT_DIR/build_bounded_image.sh"', source)
        self.assertNotIn('docker image inspect "$BOUNDED_IMAGE_REF" --format', source)

    def test_native_download_setup_uses_the_pinned_image_and_only_the_native_snapshot(self):
        source = SETUP.read_text(encoding="utf-8")
        branches = re.findall(r"native_download\)\n(?P<body>.*?)\n    ;;", source, re.DOTALL)
        self.assertEqual(len(branches), 2)
        image_branch, snapshot_branch = branches
        self.assertIn('docker pull "${IMAGE_TAG}@${IMAGE_DIGEST}"', image_branch)
        self.assertIn('BOUNDED_IMAGE_REF="$BOUNDED_IMAGE_REF" bash "$SCRIPT_DIR/build_bounded_image.sh"', image_branch)
        self.assertIn('download_snapshot "$TARGET_REPO" "$TARGET_REVISION"', snapshot_branch)
        self.assertNotIn("DRAFT_REPO", snapshot_branch)

    def test_native_mtp_measurements_and_text_only_scope_are_documented(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        results = (ROOT / "benchmarks" / "RESULTS.md").read_text(encoding="utf-8")
        for value in (
            "121.28", "127.52", "126.91", "117.84", "126.09", "123.57",
            "100008+8", "26.143", "128008+8", "40.365", "129241",
            "this-machine measurements",
        ):
            self.assertIn(value, results)
        self.assertIn("[benchmarks/RESULTS.md]", readme)
        self.assertNotIn("121.28", readme)
        self.assertIn("text-only", readme)
        self.assertIn("SGLang itself supports vision", readme)
        self.assertIn("future work", readme)

    def test_native_mtp_readme_documents_the_emitted_capacity_and_speculation_contract(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for value in (
            "memory fraction 0.96", "Mamba cache size 1",
            "EAGLE steps 3, top-k 1, and 4 draft tokens", "FP8 E4M3 KV cache",
            "prefill chunk 1,024", "radix cache off", "prefill CUDA graph off",
            "one running request", "131,072-token logical context",
            "129,241-token physical pool",
        ):
            self.assertIn(value, readme)

    def test_native_mtp_readme_links_the_public_checkpoint_and_needs_no_token(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        native_section = readme.split("### Optional native-MTP NVFP4 profile", 1)[1].split("### Private-LAN access", 1)[0]
        self.assertIn("https://huggingface.co/Shiftedx/Qwopus3.8-27B-Flash-NVFP4-MTP", native_section)
        self.assertIn("cp profiles/rtx5090-native-mtp-nvfp4.env.example profile.env", native_section)
        self.assertIn("bash scripts/setup_profile.sh", native_section)
        self.assertIn("No Hugging Face token is required", native_section)
        self.assertNotIn("HF_TOKEN", native_section)
        self.assertNotIn("Shiftedx/Qwopus3.8-27B-Flash-NVFP4-MTP-RTX5090", native_section)

    def test_native_mtp_results_record_the_current_matched_and_code_harnesses(self):
        results = (ROOT / "benchmarks" / "RESULTS.md").read_text(encoding="utf-8")
        for value in (
            "138.7309", "138.9612", "138.5336", "204.7", "32.2% slower",
            "159.6329", "159.5224", "159.8960",
            "prior 405.5 code input was unrecoverable", "not apples-to-apples",
        ):
            self.assertIn(value, results)

    def test_native_mtp_model_card_scopes_the_checkpoint_as_text_only_and_links_setup(self):
        self.assertTrue(NATIVE_MTP_MODEL_CARD.is_file())
        source = NATIVE_MTP_MODEL_CARD.read_text(encoding="utf-8")
        self.assertIn("Text-only", source)
        self.assertIn("does **not** support image or video input", source)
        self.assertIn("https://github.com/shiftedx/Qwen3.8-27B-RTX5090-SGLang-DFlash", source)
        self.assertIn("# Qwopus3.8-27B-Flash NVFP4 + MTP\n", source)
        self.assertNotIn("# Qwopus3.8-27B-Flash NVFP4 + MTP — RTX 5090", source)

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
        for forbidden in ("C:\\Users\\Kyle", "/root/src/sglang-bounded-dflash"):
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
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("*.sh text eol=lf", attributes)
        self.assertIn("*.env.example text eol=lf", attributes)

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
            "--host 0.0.0.0",
        ):
            self.assertIn(flag, result.stdout)


if __name__ == "__main__":
    unittest.main()
