"""The redactor masks secrets, not the file paths Argus itself declared (T-0019 batch 3b step 08; #107 review).

`inspect_service_config` on vm-095 returned nginx's configuration with its path shown as
`/[REDACTED HIGH-ENTROPY].conf`: the high-entropy rule (40+ characters of `[A-Za-z0-9+/_=-]`) took
`opt/argus-v18/app/deploy/lab/nginx/default` for a token. #107 exempted every run of lower-case path segments; that
also let lower-case secrets in URL paths through (an API key, a webhook, a presigned download). Now only the paths
Argus declared stay readable: the inspection policy's `service_config` and `files` entries, and the inventory's
mounts (not `/`). Everything else is masked as before #107.
"""
from __future__ import annotations

import pytest

from argus.capabilities.redaction import Redactor
from argus.infrastructure.wiring import declared_paths

NGINX = "/opt/argus-v18/app/deploy/lab/nginx/default.conf"
R = Redactor(declared=[NGINX, "/srv/argus-lab-fill/", "/var/log/myapp/", "/"])


@pytest.mark.parametrize("text", [
    f"config path={NGINX}",
    f"<config path=\"{NGINX}\">",
    "mount /srv/argus-lab-fill/some-long-directory-name/data-0007.bin",
    "file /var/log/myapp/a-rather-long-application-log-name-0001.log read",
])
def test_a_declared_path_is_not_masked(text):
    out, n = R.text(text)
    assert out == text and n == 0


@pytest.mark.parametrize("text", [
    "GET /api/v1/keys/9f86d081884c7d659a2feaa0c55ad015 200",
    "webhook https://hooks.example.com/services/t0a1b2c3d4/b9z8y7x6w5/x1y2z3w4v5u6t7s8r9q0p1o2",
    "presigned /download/a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6/e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2",
    "file /var/lib/docker/containers/argus-lab-api/hostconfig.json read",     # undeclared: masked, as before #107
])
def test_a_lower_case_secret_in_a_path_is_masked(text):
    out, n = R.text(text)
    assert "[REDACTED HIGH-ENTROPY]" in out and n >= 1


def test_the_root_mount_declares_nothing():
    out, n = Redactor(declared=["/"]).text("GET /api/v1/keys/9f86d081884c7d659a2feaa0c55ad015 200")
    assert "9f86d081" not in out and n == 1


def test_a_declared_prefix_does_not_cover_a_neighbour():
    out, _ = R.text("mount /srv/argus-lab-fill-other/9f86d081884c7d659a2feaa0c55ad015/x")
    assert "9f86d081" not in out


@pytest.mark.parametrize("secret", [
    "Xk3vQ9mZpL2wR8tY6uB1nC4dF7gH0jKsAeIoUy5T",                        # 40 random mixed-case
    "dGhpcyBpcyBhIHNlY3JldCB2YWx1ZSB0aGF0IGlzIGxvbmc+Lw==",            # base64 with + and =
    "abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdef1234",  # 64 hex
    "aGVsbG8vd29ybGQvdGhpcy9pcy9hL3Rva2VuL3dpdGgvc2xhc2hlcw/Q2xhc3M",   # base64 with / and mixed case
])
def test_a_token_is_still_masked(secret):
    out, n = R.text(f"value {secret} end")
    assert secret not in out and "[REDACTED HIGH-ENTROPY]" in out and n == 1


def test_a_token_after_a_declared_path_is_still_masked():
    out, _ = R.text(f"{NGINX} Xk3vQ9mZpL2wR8tY6uB1nC4dF7gH0jKsAeIoUy5T")
    assert NGINX in out and "Xk3vQ9mZ" not in out


def test_other_patterns_are_unchanged():
    out, _ = R.text("key sk-abcdefghijklmnopqrstuvwx and postgresql://argus:hunter2@db/x")   # brain-audit: allow (a fake key the test checks is masked)
    assert "sk-abcdef" not in out and "hunter2" not in out


def test_the_declared_paths_come_from_the_policy_and_the_inventory():
    paths = declared_paths({"inspection": {"targets": {"vm-166/container:argus-lab-nginx": {"service_config": [NGINX]},
                                                       "vm-166/host:vm-166": {"files": ["/var/log/myapp/"]}}}},
                           {"targets": [{"ref": "vm-166/host:vm-166", "mounts": ["/", "/srv/argus-lab-fill"]}]})
    assert sorted(paths) == sorted([NGINX, "/var/log/myapp/", "/srv/argus-lab-fill/"])     # "/" is not a path to keep


def test_marker_characters_in_the_input_change_nothing():
    out, _ = R.text(f"7 {NGINX}")
    assert NGINX in out and "" not in out


# --- #110 review (conantkd): a declared path counts only where a path starts, and a token under a directory is masked

SECRET = bytes(range(20)).hex()          # 40 lower-case hex, a single path segment


@pytest.mark.parametrize("text", [
    f"https://hooks.example.com/srv/argus-lab-fill/{SECRET}",   # the declared directory inside a URL
    f"/evil/srv/argus-lab-fill/{SECRET}",                        # after another path
])
def test_a_declared_path_inside_another_path_or_url_covers_nothing(text):
    out, n = R.text(text)
    assert SECRET not in out and n >= 1


def test_a_high_entropy_name_under_a_declared_directory_is_masked():
    out, n = R.text(f"/srv/argus-lab-fill/data/{SECRET}.bin")
    assert SECRET not in out and out.startswith("/srv/argus-lab-fill/data/") and n == 1


@pytest.mark.parametrize("text", [
    "/srv/argus-lab-fill/fill-0001.bin", "path=/srv/argus-lab-fill/a/b/c.log", f"'{NGINX}'", f"({NGINX})",
    "file /var/log/myapp/app-2026-10-12.log rotated",
])
def test_declared_paths_at_a_path_start_stay_readable(text):
    out, n = R.text(text)
    assert out == text and n == 0


# --- X-5: Docker's container ID under the target service's own key is an identity, not a secret ---------------------
DOCKER_ID = "ab" * 32                  # 64 lower-case hex, the shape of Docker's full Id (low entropy for the scanners)


def test_the_full_container_id_under_its_own_key_is_kept_and_nowhere_else():
    kept, n = Redactor().value({"container_id": DOCKER_ID, "id": DOCKER_ID[:12]})
    assert kept == {"container_id": DOCKER_ID, "id": DOCKER_ID[:12]} and n == 0
    masked, n = Redactor().value({"image_digest": DOCKER_ID, "note": f"id {DOCKER_ID}"})
    assert DOCKER_ID not in str(masked) and n == 2                         # another key, or free text: still masked
    assert Redactor().text(f"container_id={DOCKER_ID}")[0] != f"container_id={DOCKER_ID}"


@pytest.mark.parametrize("value", ["AB" * 32, "ab" * 33, "Zm9v" * 16])
def test_anything_else_under_container_id_is_still_masked(value):
    masked, n = Redactor().value({"container_id": value})
    assert masked["container_id"] == "[REDACTED HIGH-ENTROPY]" and n == 1
