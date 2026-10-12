"""The redactor masks secrets, not file paths (found in T-0019 batch 3b step 08).

`inspect_service_config` on vm-095 returned nginx's configuration with its path shown as
`/[REDACTED HIGH-ENTROPY].conf`: the high-entropy rule (40+ characters of `[A-Za-z0-9+/_=-]`) took
`opt/argus-v18/app/deploy/lab/nginx/default` for a token. A run of lower-case path segments (each at most 32
characters, no `+` or `=`) is a path and stays; tokens — mixed case, base64 with `+`/`=`, long hex, `sk-` keys,
URL credentials — are still masked.
"""
from __future__ import annotations

import pytest

from argus.capabilities.redaction import Redactor

R = Redactor()


@pytest.mark.parametrize("text", [
    "config path=/opt/argus-v18/app/deploy/lab/nginx/default.conf",
    "file /var/lib/docker/containers/argus-lab-api/hostconfig.json read",
    "mount /srv/argus-lab-fill/some-long-directory-name/data-0007.bin",
])
def test_a_file_path_is_not_masked(text):
    out, n = R.text(text)
    assert out == text and n == 0


@pytest.mark.parametrize("secret", [
    "Xk3vQ9mZpL2wR8tY6uB1nC4dF7gH0jKsAeIoUy5T",                        # 40 random mixed-case
    "dGhpcyBpcyBhIHNlY3JldCB2YWx1ZSB0aGF0IGlzIGxvbmc+Lw==",            # base64 with + and =
    "abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdef1234",  # 64 hex
    "aGVsbG8vd29ybGQvdGhpcy9pcy9hL3Rva2VuL3dpdGgvc2xhc2hlcw/Q2xhc3M",   # base64 with / and mixed case
])
def test_a_token_is_still_masked(secret):
    out, n = R.text(f"value {secret} end")
    assert secret not in out and "[REDACTED HIGH-ENTROPY]" in out and n == 1


def test_other_patterns_are_unchanged():
    out, _ = R.text("key sk-abcdefghijklmnopqrstuvwx and postgresql://argus:hunter2@db/x")   # brain-audit: allow (a fake key the test checks is masked)
    assert "sk-abcdef" not in out and "hunter2" not in out
