r"""The Bearer rule must not take a named secret's key for its token (found by the OP-014 property test on main 096bf90).

`Bearer\npassword=hunter2xyz` came out as `Bearer [REDACTED]hunter2xyz`: `\s+` crossed the newline, the token class
(no `=`) matched `password` and the value stayed in clear, on its way to the model context. A named secret after
`Bearer`, on the same line or the next, is now left to the named-secret rule; a real token is still masked.
"""
from __future__ import annotations

import pytest

from argus.capabilities.redaction import Redactor


@pytest.mark.parametrize("text, key, secret", [
    ("Bearer\npassword=hunter2xyz\n", "password", "hunter2xyz"),
    ("BEARER\npassword=0\n", "password", "0"),
    ("Bearer password=hunter2xyz", "password", "hunter2xyz"),
    ("bearer\t api_key: s3cr3tvalue", "api_key", "s3cr3tvalue"),
    ("Authorization: Bearer\nDB_PASSWORD = 'pa ss'", "DB_PASSWORD", "pa ss"),
])
def test_a_named_secret_after_bearer_keeps_its_value_masked(text, key, secret):
    out, n = Redactor().text(text)
    assert f"{key}=[REDACTED]" in out and n >= 1, out
    assert not out.rstrip().endswith(secret), out


@pytest.mark.parametrize("token", ["abcdefgh12345678", "eyJhbGciOiJIUzI1NiJ9.e30.sig_-~+/x", "dG9rZW5wYWRkZWQ=",
                                   "mytokenvalue0123==", "secretive.token.value"])
def test_a_real_bearer_token_is_still_masked(token):
    out, n = Redactor().text(f"Authorization: Bearer {token} end")
    assert token not in out and "Bearer [REDACTED]" in out and n >= 1, out


@pytest.mark.parametrize("text", ["Authorization: Bearer\nabc123def456ghi", "bearer\r\n  abc123def456ghi end"])
def test_a_short_token_on_the_next_line_is_still_masked(text):
    # #278 review: over-masking the line after "Bearer" is better than a short token in clear (the high-entropy rule
    # needs 40+ characters)
    out, n = Redactor().text(text)
    assert "abc123def456ghi" not in out and "Bearer [REDACTED]" in out and n >= 1, out
