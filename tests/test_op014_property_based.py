"""OP-014 step 10: property-based tests (Hypothesis) for the redaction and the target parsing. The example tests check
the cases someone thought of; these generate many inputs and check what must hold for every one of them."""
from __future__ import annotations

import string

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from argus.capabilities.redaction import Redactor
from argus.domain.model import TARGET_KINDS, TargetRef

SETTINGS = settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])

# Text around a secret: printable ASCII and a few non-ASCII letters, spaces and punctuation.
filler = st.text(alphabet=string.printable + "áéñüßж中", max_size=60)
token = st.text(alphabet=string.ascii_letters + string.digits, min_size=40, max_size=80)
value = st.text(alphabet=string.ascii_letters + string.digits + "!#$%&*+-.^_~", min_size=1, max_size=40)
SECRET_NAMES = ["password", "passwd", "pwd", "secret", "token", "api_key", "apikey", "access_key", "DB_PASSWORD",
                "x.api-key"]


# --- redaction ---------------------------------------------------------------------------------------------------------
@SETTINGS
@given(before=filler, secret=token, after=filler)
def test_a_long_token_never_survives_in_any_text(before, secret, after):
    """Glued to its neighbours, too: a non-ASCII letter next to a token was a word character for Unicode `\b`, so the
    high-entropy rule saw no word boundary and let the token through (found by this test)."""
    for text in (f"{before} {secret} {after}", f"{before}{secret}{after}"):
        out, _ = Redactor().text(text)
        assert secret not in out


@pytest.mark.parametrize("left, right", [("é", ""), ("", "é"), ("ж", "中"), ("ñ", " "), ("ü", "ß")])
def test_a_token_next_to_a_non_ascii_letter_is_masked(left, right):
    secret = "Ab3" * 14
    for text in (f"{left}{secret}{right}", f"clé {left}sk-{secret[:20]}{right}"):
        out, n = Redactor().text(text)
        assert secret[:20] not in out and n >= 1


@SETTINGS
@given(before=filler, name=st.sampled_from(SECRET_NAMES), sep=st.sampled_from(["=", ": ", " = ", ":"]), secret=value,
       quote=st.sampled_from(["", '"', "'"]), after=filler)
def test_a_named_secret_is_masked_whatever_its_value(before, name, sep, secret, quote, after):
    out, n = Redactor().text(f"{before}\n{name}{sep}{quote}{secret}{quote} \n{after}")
    assert n >= 1 and f"{name}=[REDACTED]" in out
    assert f"{name}{sep}{quote}{secret}" not in out


@SETTINGS
@given(before=filler, secret=st.text(alphabet=string.ascii_letters + string.digits + "._~+/-", min_size=8, max_size=60),
       after=filler)
def test_a_bearer_token_is_masked(before, secret, after):
    out, _ = Redactor().text(f"{before} Authorization: Bearer {secret} \n{after}")
    assert f"Bearer {secret}" not in out and "Bearer [REDACTED]" in out


@SETTINGS
@given(scheme=st.sampled_from(["postgres", "postgresql", "mysql", "redis", "mongodb", "amqp"]),
       user=st.text(alphabet=string.ascii_lowercase + string.digits, min_size=1, max_size=12),
       pw=st.text(alphabet=string.ascii_letters + string.digits + "!#$%^&*", min_size=1, max_size=30))
def test_a_password_in_a_connection_url_is_masked(scheme, user, pw):
    out, _ = Redactor().text(f"connect {scheme}://{user}:{pw}@db.internal:5432/app")
    assert f":{pw}@" not in out and f"{scheme}://[REDACTED]@" in out


@SETTINGS
@given(text=st.text(max_size=200))
def test_redacting_twice_changes_nothing_more(text):
    r = Redactor(["/etc/app/", "/srv/data.conf"])
    once, _ = r.text(text)
    twice, _ = r.text(once)
    assert twice == once


@SETTINGS
@given(text=st.text(alphabet=string.digits + " .,;()[]\n", max_size=200))
def test_text_without_anything_secret_like_is_unchanged(text):
    assert Redactor().text(text) == (text, 0)


secret_key = st.sampled_from(["password", "db_secret", "TOKEN", "api_key", "private-key", "env", "my_apikey"])
plain = st.one_of(st.integers(), st.booleans(), st.none(), st.text(alphabet=string.ascii_lowercase, max_size=10))
nested = st.recursive(plain, lambda kids: st.one_of(st.lists(kids, max_size=4),
                                                    st.dictionaries(st.sampled_from(["a", "b", "items"]), kids, max_size=3)),
                      max_leaves=12)


@SETTINGS
@given(key=secret_key, secret=plain, outer=nested, path=st.lists(st.sampled_from(["a", "b", 0]), max_size=4))
def test_a_secret_key_is_masked_at_any_depth(key, secret, outer, path):
    doc = {key: secret}
    for step in reversed(path):                            # bury it under dicts and lists
        doc = [outer, doc] if step == 0 else {step: doc, "other": outer}
    out, n = Redactor().value(doc)
    for step in path:
        out = out[1] if step == 0 else out[step]
    assert out[key] == "[REDACTED]" and n >= 1


@SETTINGS
@given(name=st.text(alphabet=string.ascii_lowercase + "-_", min_size=1, max_size=20), before=filler)
def test_a_declared_directory_keeps_its_files_readable(name, before):
    path = f"/etc/argus-lab/{name}.conf"
    out, _ = Redactor(["/etc/argus-lab/"]).text(f"{before} read {path} ok")
    assert path in out


# --- target parsing ----------------------------------------------------------------------------------------------------
host = st.text(alphabet=string.ascii_letters + string.digits + "-_.", min_size=1, max_size=20)
name = st.text(alphabet=string.ascii_letters + string.digits + "-_.:/", min_size=1, max_size=30)


@SETTINGS
@given(h=host, kind=st.sampled_from(sorted(TARGET_KINDS)), n=name)
def test_a_target_parses_back_to_itself(h, kind, n):
    ref = TargetRef(host=h, kind=kind, name=n)
    assert TargetRef.parse(str(ref)) == ref


@SETTINGS
@given(text=st.text(max_size=60))
def test_parsing_any_text_gives_a_target_or_a_value_error(text):
    try:
        ref = TargetRef.parse(text)
    except ValueError:
        return
    assert ref.host and ref.name and ref.kind in TARGET_KINDS and "/" not in ref.host
    assert str(ref) == text


@pytest.mark.parametrize("bad", ["", "h1", "h1/", "/container:x", "h1/container:", "h1/robot:x", "h1:container/x"])
def test_known_bad_targets_are_refused(bad):
    with pytest.raises(ValueError):
        TargetRef.parse(bad)
