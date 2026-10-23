"""OP-014 step 9: tests written from the survivors of a mutation run (mutmut 3.3.1) on `argus/capabilities/redaction.py`.

The high-entropy rule masks any run of 40+ path or token characters; the paths Argus declared stay readable (a file
exactly, a directory with what lies under it, unless a segment holds a token). Each test pins a property a mutant could
change without any other test failing.
"""
from __future__ import annotations

from argus.capabilities.redaction import Redactor

MARK = "[REDACTED HIGH-ENTROPY]"
DIR = "/var/log/myapp/"
SUB = "/var/log/myapp/service_events_archive_long_retention/current"   # its part under DIR alone is 45 characters
FILE = "/srv/application_configuration_files/settings"            # 45 path characters
TOKEN = "Ab3x" * 10                                                # 40 token characters (low entropy: no secret-scan hit)


def test_a_path_under_a_declared_directory_stays_readable_wherever_it_appears():
    r = Redactor([DIR])
    for text in (f"tail {SUB}", f"{SUB} and again {SUB}", f"{SUB} {SUB} {SUB}", f"x\n{SUB}\n"):
        assert r.text(text) == (text, 0)
    assert r.text(SUB.replace("myapp", "other")) == ("/" + MARK, 1)  # the same shape, undeclared: masked


def test_a_token_segment_under_a_declared_directory_is_still_masked():
    out, n = Redactor([DIR]).text(f"{DIR}{TOKEN}/x")
    assert TOKEN not in out and n == 1


def test_a_declared_file_alone_is_kept_even_with_no_directory_declared():
    for text in (f"read {FILE}.yaml", f"{FILE}.yaml {FILE}.yaml", f"{FILE}.yaml {FILE}.yaml {FILE}.yaml"):
        assert Redactor([FILE + ".yaml"]).text(text) == (text, 0)
    assert Redactor([]).text(f"read {FILE}.yaml") == (f"read /{MARK}.yaml", 1)


def test_a_declared_file_counts_only_where_a_path_starts_and_as_the_whole_name():
    r = Redactor([FILE])
    assert r.text(f"https://evil.example{FILE}")[1] == 1             # inside a URL: not the declared file
    for suffix in ("_old", "Old", "old", "/more"):                   # a longer name is another file
        out, n = r.text(f"{FILE}{suffix}")
        assert n == 1 and out.startswith("/" + MARK), suffix
    assert r.text(f"{FILE}.bak") == (f"{FILE}.bak", 0)               # a dot ends the name


def test_overlapping_declared_spans_give_back_the_text_unchanged():
    file = f"{DIR}service_events_archive_long/current.log"
    for declared in ([DIR, file], [file, DIR]):
        r = Redactor(declared)
        for text in (f"tail {file}", f"{file} then {file}", f"{DIR}{TOKEN}/f {file}"):
            out, n = r.text(text)
            assert out.count("current.log") == text.count("current.log") and "service_events" in out
            if TOKEN not in text:
                assert (out, n) == (text, 0)


def test_a_declared_file_that_holds_a_token_is_kept_whole_over_its_directory():
    file = f"{DIR}x/{TOKEN}/f"
    assert Redactor([DIR, file]).text(f"cat {file}") == (f"cat {file}", 0)


def test_markers_in_the_input_are_neutralised_never_used_to_restore_a_part():
    r = Redactor([FILE])
    out, n = r.text(f"a0b {FILE}")
    assert out == f"a�0�b {FILE}" and n == 0


def test_each_masked_token_is_counted_and_the_marker_is_exact():
    out, n = Redactor().text(f"{TOKEN} and {TOKEN}")
    assert (out, n) == (f"{MARK} and {MARK}", 2)


def test_value_counts_every_redaction_and_nothing_else():
    r = Redactor()
    assert r.value(5) == (5, 0)
    assert r.value({"a": "plain"}) == ({"a": "plain"}, 0)
    assert r.value(["plain", "text"]) == (["plain", "text"], 0)
    assert r.value({"password": "x", "api_key": "y"}) == ({"password": "[REDACTED]", "api_key": "[REDACTED]"}, 2)
    out, n = r.value({"password": "x", "note": TOKEN})                 # keys after a secret one are still read
    assert out == {"password": "[REDACTED]", "note": MARK} and n == 2
    assert r.value([TOKEN, TOKEN]) == ([MARK, MARK], 2)
