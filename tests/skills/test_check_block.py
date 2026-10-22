"""Exercise the static CLI and a local template simulation; never run fixture commands."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".claude" / "skills" / "code-bash-step"
CHECKER = SKILL / "scripts" / "check_block.py"
FIXTURES = Path(__file__).with_name("fixtures")

TRAPS = {
    "missing-label": "missing block label",
    "location-tag": "missing or invalid location tag",
    "missing-expected": "missing Expected: line",
    "missing-set-location": "missing Set-Location",
    "missing-repository-check": "missing git rev-parse --show-toplevel",
    "missing-ok-counter": "missing $ok = 0",
    "missing-verdict": "missing final PASS/FAIL verdict",
    "verdict-label": "verdict label does not match",
    "verdict-denominator": "verdict counts do not match",
    "native-quotes": "double quotes inside native command arguments",
    "braced-colon": "unsafe variable-colon interpolation",
    "unbraced-colon": "unsafe variable-colon interpolation",
    "newline-else": "top-level else/elseif must follow } on the same line",
    "newline-elseif": "top-level else/elseif must follow } on the same line",
    "powershell-here-string": "here-string/heredoc is not allowed",
    "bash-heredoc": "here-string/heredoc is not allowed",
    "vm-exit": "exit is not allowed in a VM block",
    "vm-reboot": "reboot is not allowed in a VM block",
    "vm-missing-session": "mutation requires a preceding SESSION check",
    "vm-late-session": "mutation requires a preceding SESSION check",
    "vm-single-quote-backslash": "mutation requires a preceding SESSION check",
    "ipv4": "IPv4 address is not allowed",
    "token-assignment": "secret/token/password assignment is not allowed",
    "password-assignment": "secret/token/password assignment is not allowed",
    "duplicate-labels": "duplicate block label",
}


def fixture_text(name: str) -> str:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    # A documentation-only address is assembled at test time, never stored as a host address.
    return text.replace("__TEST_IPV4__", ".".join(map(str, (192, 0, 2, 9))))


def run_checker(tmp_path: Path, text: str, *, bom: bool = False) -> subprocess.CompletedProcess[str]:
    source = tmp_path / "code.bash"
    source.write_bytes(text.encode("utf-8-sig" if bom else "utf-8"))
    return subprocess.run(
        [sys.executable, "-I", str(CHECKER), str(source)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=10,
    )


@pytest.mark.parametrize("fixture", sorted(FIXTURES.glob("valid-*.bash")), ids=lambda p: p.stem)
def test_accepts_known_good_blocks(tmp_path, fixture):
    result = run_checker(tmp_path, fixture_text(fixture.name))
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == result.stderr == ""


@pytest.mark.parametrize("trap, message", TRAPS.items(), ids=list(TRAPS))
def test_rejects_known_traps(tmp_path, trap, message):
    text = fixture_text(f"invalid-{trap}.bash")
    result = run_checker(tmp_path, text)
    assert result.returncode == 1, result.stdout + result.stderr
    assert message in result.stdout
    assert result.stderr == ""
    for line in result.stdout.splitlines():
        assert ": " in line, "Each diagnostic must identify its block."
    expected_label = "VM.1" if trap.startswith("vm-") or trap == "bash-heredoc" else "AN.2"
    if trap == "missing-label":
        expected_label = "UNLABELLED"
    assert any(line.startswith(expected_label + ": ") for line in result.stdout.splitlines())


def test_accepts_all_real_blocks_in_one_file(tmp_path):
    text = "\n".join(
        fixture_text(f"valid-{name}.bash")
        for name in ("comment", "approve-on-head", "commit-push-open-pr")
    )
    result = run_checker(tmp_path, text)
    assert result.returncode == 0, result.stdout + result.stderr


def test_status_comments_between_blocks_are_free_text(tmp_path):
    text = fixture_text("valid-comment.bash")
    text += "\n# AN.1 approved an earlier PR; AN.2 commented.\n"
    text += fixture_text("valid-approve-on-head.bash")
    result = run_checker(tmp_path, text)
    assert result.returncode == 0, result.stdout + result.stderr


def test_accepts_inline_rule_header_from_policy(tmp_path):
    text = fixture_text("valid-vm-readonly.bash").replace("# VM.1 [", "# --- VM.1 [", 1)
    result = run_checker(tmp_path, text)
    assert result.returncode == 0, result.stdout + result.stderr


def test_rejects_header_without_block_separator(tmp_path):
    text = fixture_text("valid-comment.bash")
    text = "\n".join(text.splitlines()[1:]) + "\n"
    result = run_checker(tmp_path, text)
    assert result.returncode == 1
    assert "missing labelled block header" in result.stdout


def test_accepts_powershell_bom_crlf_and_output_strings(tmp_path):
    text = fixture_text("valid-comment.bash")
    text = text.replace("$ok = 0", '$ok = 0\n"PR: $url"\n"literal } else { and git are output"')
    result = run_checker(tmp_path, text.replace("\n", "\r\n"), bom=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "command",
    [
        'git log --format="%H"',
        '$url = gh pr view 254 --jq \'.url + "text"\'',
        'if ($true) { docker ps --format \'{{.Names}} "text"\' }',
        '& ..\\argus_production\\.venv\\Scripts\\python.exe -c \'print("text")\'',
        'gh pr view 254 `\n  --jq \'.url + "text"\'',
    ],
)
def test_detects_native_quotes_at_command_positions(tmp_path, command):
    text = fixture_text("valid-comment.bash").replace("$ok = 0", "$ok = 0\n" + command)
    result = run_checker(tmp_path, text)
    assert result.returncode == 1
    assert "double quotes inside native command arguments" in result.stdout


def test_does_not_treat_comments_and_output_as_commands(tmp_path):
    text = fixture_text("valid-comment.bash").replace(
        "$ok = 0", '$ok = 0\n# gh pr view "example"\nWrite-Output \'git "quoted output"\''
    )
    result = run_checker(tmp_path, text)
    assert result.returncode == 0, result.stdout + result.stderr


def test_header_expected_text_does_not_replace_executable_verdict(tmp_path):
    text = fixture_text("valid-comment.bash")
    text = "\n".join(line for line in text.splitlines() if not line.startswith("if ($ok -eq")) + "\n"
    result = run_checker(tmp_path, text)
    assert result.returncode == 1
    assert "missing final PASS/FAIL verdict" in result.stdout


def test_rejects_commands_outside_a_labelled_block(tmp_path):
    result = run_checker(tmp_path, "git status\n" + fixture_text("valid-comment.bash"))
    assert result.returncode == 1
    assert "UNLABELLED: " in result.stdout


@pytest.mark.parametrize("text", ["", "# A note without a block\n", "git status\n"])
def test_rejects_files_without_blocks(tmp_path, text):
    result = run_checker(tmp_path, text)
    assert result.returncode == 1
    assert "UNLABELLED: " in result.stdout


def test_reports_all_problems_and_never_echoes_sensitive_values(tmp_path):
    text = fixture_text("invalid-native-quotes.bash") + "\n$api_token = 'synthetic-fixture-value'\n"
    result = run_checker(tmp_path, text)
    assert result.returncode == 1
    assert "double quotes inside native command arguments" in result.stdout
    assert "secret/token/password assignment is not allowed" in result.stdout
    assert "synthetic-fixture-value" not in result.stdout + result.stderr


@pytest.mark.parametrize("mutation", ["touch /opt/argus-v18/example", "printf sample > /opt/argus-v18/example"])
def test_vm_mutation_is_allowed_only_inside_successful_session_guard(tmp_path, mutation):
    text = fixture_text("valid-vm-readonly.bash")
    text = text.replace("  cat /opt/argus-v18/DEPLOYED", "  " + mutation)
    result = run_checker(tmp_path, text)
    assert result.returncode == 0, result.stdout + result.stderr
    # A check's failure branch does not authorize writes.
    text = text.replace("else\n", "else\n  " + mutation + "\n", 1)
    result = run_checker(tmp_path, text)
    assert result.returncode == 1
    assert "mutation requires a preceding SESSION check" in result.stdout


def test_vm_session_mention_in_a_comment_is_not_a_guard(tmp_path):
    text = fixture_text("invalid-vm-missing-session.bash")
    text = text.replace("sudo touch", "# if grep -q 'holder=example' /opt/argus-v18/SESSION; then\nsudo touch")
    result = run_checker(tmp_path, text)
    assert result.returncode == 1
    assert "mutation requires a preceding SESSION check" in result.stdout


@pytest.mark.parametrize(
    "command",
    [
        "find /opt/argus-v18/example -delete",
        "ip link set argus-fixture down",
        "sort -o /opt/argus-v18/sorted /opt/argus-v18/input",
        "docker ps $(touch /opt/argus-v18/example)",
        'printf \'%s\' "$(touch /opt/argus-v18/example)"',
        "cat /opt/argus-v18/DEPLOYED >& /opt/argus-v18/example",
    ],
)
def test_rejects_unguarded_vm_mutation_in_read_looking_commands(tmp_path, command):
    text = fixture_text("invalid-vm-missing-session.bash").replace("sudo touch /opt/argus-v18/example", command)
    result = run_checker(tmp_path, text)
    assert result.returncode == 1
    assert "mutation requires a preceding SESSION check" in result.stdout


def test_accepts_second_vm_location(tmp_path):
    text = fixture_text("valid-vm-readonly.bash").replace("vm-095", "vm-166")
    result = run_checker(tmp_path, text)
    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_reads_input_without_executing_it(tmp_path):
    sentinel = tmp_path / "must-not-exist"
    text = fixture_text("valid-comment.bash").replace("$ok = 0", f"$ok = 0\nNew-Item -Path '{sentinel}'")
    result = run_checker(tmp_path, text)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not sentinel.exists()


def test_missing_input_has_a_sanitized_diagnostic(tmp_path):
    result = subprocess.run(
        [sys.executable, "-I", str(CHECKER), str(tmp_path / "missing.bash")],
        capture_output=True, text=True, check=False, timeout=10,
    )
    assert result.returncode == 1
    assert "UNLABELLED: cannot read input" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr


@pytest.mark.parametrize("template", ["approve-on-head.ps1", "comment.ps1", "commit-push-open-pr.ps1", "vm-readonly.sh"])
def test_supplied_templates_satisfy_the_static_contract(tmp_path, template):
    result = run_checker(tmp_path, (SKILL / "templates" / template).read_text(encoding="utf-8"))
    assert result.returncode == 0, result.stdout + result.stderr


def vm_block(commands: str) -> str:
    return (
        "# --------------------------------------------------------------\n"
        "# VM.1 [VM vm-095 · bash] Local checker test data\n"
        "# Expected: only authorized SESSION forms pass.\n" + commands + "\n"
    )


@pytest.mark.parametrize("option", ["-q", "-Eq"])
def test_accepts_anchored_session_holder_guard(tmp_path, option):
    text = vm_block(
        f"if grep {option} '^holder=example ' /opt/argus-v18/SESSION; then\n"
        "  sudo touch /opt/argus-v18/example\nfi"
    )
    result = run_checker(tmp_path, text)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("option", ["-vq", "--invert-match -q", "-Lq"])
def test_rejects_session_guard_that_succeeds_for_another_holder(tmp_path, option):
    text = vm_block(
        f"if grep {option} 'holder=example' /opt/argus-v18/SESSION; then\n"
        "  sudo touch /opt/argus-v18/example\nfi"
    )
    result = run_checker(tmp_path, text)
    assert result.returncode == 1
    assert "mutation requires a preceding SESSION check" in result.stdout


@pytest.mark.parametrize("option, pattern", [("-q", "holder=example"), ("-q", "^holder=example"), (
    "-qx", "holder=example"
)])
def test_rejects_session_holder_guard_without_a_real_holder_boundary(tmp_path, option, pattern):
    text = vm_block(
        f"if grep {option} '{pattern}' /opt/argus-v18/SESSION; then\n"
        "  sudo touch /opt/argus-v18/example\nfi"
    )
    result = run_checker(tmp_path, text)
    assert result.returncode == 1
    assert "mutation requires a preceding SESSION check" in result.stdout


@pytest.mark.parametrize("option", ["-Fxq", "--quiet --fixed-strings --line-regexp"])
def test_accepts_full_two_field_session_line_guard(tmp_path, option):
    text = vm_block(
        f"if grep {option} 'holder=example session=fixture-01' /opt/argus-v18/SESSION; then\n"
        "  sudo touch /opt/argus-v18/example\nfi"
    )
    result = run_checker(tmp_path, text)
    assert result.returncode == 0, result.stdout + result.stderr


SESSION_WRITE = "echo 'holder=example session=fixture-01' | sudo tee /opt/argus-v18/SESSION"


@pytest.mark.parametrize("suffix", ["", "\ncat /opt/argus-v18/DEPLOYED", (
    "\nif grep -q '^holder=example ' /opt/argus-v18/SESSION; then\n"
    "  sudo touch /opt/argus-v18/example\nfi"
)])
def test_accepts_one_initial_literal_session_marker_write(tmp_path, suffix):
    result = run_checker(tmp_path, vm_block(SESSION_WRITE + suffix))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("redirect", [">/dev/null", "> /dev/null"])
def test_accepts_initial_session_marker_stdout_to_dev_null(tmp_path, redirect):
    result = run_checker(tmp_path, vm_block(SESSION_WRITE + " " + redirect + "\ncat /opt/argus-v18/DEPLOYED"))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("commands", [
    "cat /opt/argus-v18/DEPLOYED\n" + SESSION_WRITE,
    SESSION_WRITE + "\n" + SESSION_WRITE,
    SESSION_WRITE + "\nsudo touch /opt/argus-v18/example",
    SESSION_WRITE + "; sudo touch /opt/argus-v18/example",
    SESSION_WRITE + " && sudo touch /opt/argus-v18/example",
    SESSION_WRITE.replace("sudo tee", "sudo tee -a"),
    SESSION_WRITE.replace("sudo tee", "tee"),
    SESSION_WRITE.replace("/opt/argus-v18/SESSION", "/tmp/SESSION"),
    SESSION_WRITE.replace("/opt/argus-v18/SESSION", "/opt/argus-v18/SESSION.extra"),
    SESSION_WRITE + " > /opt/argus-v18/example",
    SESSION_WRITE + " >>/dev/null",
    SESSION_WRITE + " 2>/dev/null",
    SESSION_WRITE + " >/dev/null >/dev/null",
    SESSION_WRITE + " >/dev/null\nsudo touch /opt/argus-v18/example",
    SESSION_WRITE.replace("'holder=example session=fixture-01'", '"holder=example session=$USER"'),
    SESSION_WRITE.replace(" session=fixture-01", ""),
    SESSION_WRITE.replace("fixture-01", "fixture-01 extra=value"),
    SESSION_WRITE.replace(" | ", " | \\\n"),
])
def test_initial_marker_exception_never_authorizes_other_unguarded_writes(tmp_path, commands):
    result = run_checker(tmp_path, vm_block(commands))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "mutation requires a preceding SESSION check" in result.stdout


@pytest.mark.parametrize("holder, allowed", [("example", True), ("other", False), ("example-long", False)])
def test_readonly_template_checks_the_real_two_field_session_marker(tmp_path, holder, allowed):
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("Bash is required for the local template simulation")
    session = tmp_path / "SESSION"
    deployed = tmp_path / "DEPLOYED"
    trace = tmp_path / "local-sudo-call"
    session.write_text(f"holder={holder} session=fixture-01\n", encoding="utf-8")
    deployed.write_text("fixture-commit\n", encoding="utf-8")
    # Replace every VM path and intercept sudo locally; no connection or VM command can run.
    template = (SKILL / "templates" / "vm-readonly.sh").read_text(encoding="utf-8")
    local = template.replace("__SESSION_HOLDER__", "example")
    local = local.replace("/opt/argus-v18/SESSION", shlex.quote(session.as_posix()))
    local = local.replace("/opt/argus-v18/DEPLOYED", shlex.quote(deployed.as_posix()))
    stub = "sudo() { printf '%s\\n' local-stub > " + shlex.quote(trace.as_posix()) + "; }\n"
    result = subprocess.run([bash, "-c", stub + local], capture_output=True, text=True, check=False, timeout=10)
    assert result.returncode == 0, result.stderr
    assert trace.exists() is allowed
    if allowed:
        assert "fixture-commit" in result.stdout
        assert "VERDICT: CB.1 PASS" in result.stdout
    else:
        assert "fixture-commit" not in result.stdout
        assert "VERDICT: CB.1 STOP: NOT YOUR SESSION" in result.stdout
