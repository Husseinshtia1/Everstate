from everstate.claude_atspi_probe import _parse_gvariant_bool


def test_parse_gvariant_bool_true() -> None:
    assert _parse_gvariant_bool("(<true>,)") is True


def test_parse_gvariant_bool_false() -> None:
    assert _parse_gvariant_bool("(<false>,)") is False


def test_parse_gvariant_bool_unknown() -> None:
    assert _parse_gvariant_bool("()") is None
