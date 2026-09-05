from everstate.provider_readiness import ProviderState, classify_provider_failure


def test_claude_weekly_limit_is_limit_reached() -> None:
    output = "You've hit your weekly limit · resets Sep 7, 6pm (Asia/Jerusalem)"
    assert classify_provider_failure(output, 1) is ProviderState.LIMIT_REACHED
