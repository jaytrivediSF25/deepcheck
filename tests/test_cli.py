import pytest

from deepcheck.cli import build_parser, normalize_argv


class TestNormalizeArgv:
    def test_bare_url_gets_check_prepended(self):
        assert normalize_argv(["https://youtu.be/abc12345678"]) == [
            "check",
            "https://youtu.be/abc12345678",
        ]

    def test_explicit_subcommand_untouched(self):
        for cmd in ("check", "transcribe"):
            assert normalize_argv([cmd, "abc"]) == [cmd, "abc"]

    def test_flag_value_is_not_mistaken_for_a_subcommand(self):
        # Regression: scanning for the first non-flag token treated `max` (the
        # value of --effort) as the subcommand slot.
        assert normalize_argv(["--effort", "max", "abc"]) == [
            "check",
            "--effort",
            "max",
            "abc",
        ]

    def test_help_is_left_alone(self):
        assert normalize_argv(["--help"]) == ["--help"]

    def test_empty(self):
        assert normalize_argv([]) == []


class TestParsing:
    def test_transcribe_keeps_its_url(self):
        # Regression: an optional subcommand plus a duplicated `url` positional
        # on the parent parser silently reset url to None.
        args = build_parser().parse_args(normalize_argv(["transcribe", "abc12345678"]))
        assert args.command == "transcribe"
        assert args.url == "abc12345678"

    def test_bare_url_routes_to_check(self):
        args = build_parser().parse_args(normalize_argv(["abc12345678"]))
        assert args.command == "check"
        assert args.url == "abc12345678"
        assert args.format == "md"

    def test_check_flags(self):
        args = build_parser().parse_args(
            normalize_argv(["abc", "--max-claims", "5", "-f", "md,html", "--effort", "max"])
        )
        assert args.max_claims == 5
        assert args.format == "md,html"
        assert args.effort == "max"

    def test_missing_url_exits(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["check"])


class TestErrorMessages:
    """API faults should read as advice, not as a traceback."""

    def _http_error(self, cls, message, status):
        import httpx
        from deepcheck.cli import describe_api_error

        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        response = httpx.Response(status, request=request, json={"error": {"message": message}})
        return describe_api_error(cls(message, response=response, body=None))

    def test_no_credits_is_explained(self):
        import anthropic

        out = self._http_error(
            anthropic.BadRequestError, "Your credit balance is too low", 400
        )
        assert "no credits" in out
        assert "transcribe" in out  # tell them what still works

    def test_auth_failure_names_both_paths(self):
        import anthropic

        out = self._http_error(anthropic.AuthenticationError, "bad key", 401)
        assert "ANTHROPIC_API_KEY" in out and "ant auth login" in out

    def test_rate_limit_suggests_concurrency(self):
        import anthropic

        out = self._http_error(anthropic.RateLimitError, "slow down", 429)
        assert "--concurrency" in out

    def test_unrelated_exception_is_not_swallowed(self):
        from deepcheck.cli import describe_api_error

        assert describe_api_error(ValueError("boom")) is None
