from app.decisions import parse_line, split_timestamp

TS = "2026-10-05T18:00:01.123456789Z"
LINE = (TS + " [policy-router] {'policy': 'chain', 'requested': 'auto', "
        "'routed_to': 'local-fast', 'decided_by': 'namespace', "
        "'chain': ['namespace: restricted payments (found by hint) -> LOCAL'], "
        "'reason': 'namespace: restricted payments (found by hint) -> LOCAL', 'team': 'agents', "
        "'prompt_chars': 12000, 'sota_cap': 150000, 'ns_restricted': ['payments'], "
        "'ns_source': 'hint', 'namespaces': ['payments'], 'ns_labels_loaded': True}")


def test_parse_a_namespace_decision():
    ev = parse_line(LINE)
    assert ev["ts"] == TS
    assert ev["destination"] == "local"
    assert ev["decided_by"] == "namespace"
    assert ev["ns_restricted"] == ["payments"]
    assert ev["namespaces"] == ["payments"]
    assert ev["prompt_chars"] == 12000


def test_parse_a_sota_decision_without_namespace_fields():
    line = ("[policy-router] {'policy': 'chain', 'requested': 'auto', "
            "'routed_to': 'sota-smart', 'decided_by': 'all-sota', 'chain': [], "
            "'reason': 'privacy: score 0.00', 'team': 'research'}")
    ev = parse_line(line)
    assert ev["destination"] == "external"
    assert ev["namespaces"] == [] and ev["ns_restricted"] == []
    assert ev["ts"] == ""


def test_fail_closed_line_has_no_decided_by():
    line = ("[policy-router] {'policy': 'chain', 'routed_to': 'local-fast', "
            "'reason': 'chain: fail-closed on error (x) -> LOCAL'}")
    assert parse_line(line)["decided_by"] == "fail-closed"


def test_other_lines_are_ignored():
    for line in ("[policy-router] metrics on :9091/metrics",
                 "[policy-router] namespace labels: restricted=['payments'] unknown_values=[]",
                 "INFO: 10.0.0.1 - POST /v1/chat/completions 200",
                 "[policy-router] {not a dict",
                 "[policy-router] {'no': 'routed_to'}",
                 "[policy-router] {'routed_to': 'x', 'evil': __import__('os')}",
                 TS + " [policy-router] " + "{" + "'a': 1, " * 5000 + "'routed_to': 'x'}"):
        assert parse_line(line) is None


def test_split_timestamp():
    assert split_timestamp(TS + " hello world") == (TS, "hello world")
    assert split_timestamp("hello world") == ("", "hello world")
