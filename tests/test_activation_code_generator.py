"""Unit tests for activation code generation."""

from api.app.security import activation_code_generator


def test_generate_activation_code_returns_four_digits() -> None:
    """Generated code must keep API format expectations."""
    code = activation_code_generator.generate_activation_code()
    assert len(code) == 4
    assert code.isdigit()


def test_generate_activation_code_uses_secrets_choice(monkeypatch) -> None:
    """Generation should rely on cryptographic randomness API."""
    selected_digits = iter(["1", "2", "3", "4"])

    def _fake_choice(chars: str) -> str:
        assert chars == "0123456789"
        return next(selected_digits)

    monkeypatch.setattr(activation_code_generator.secrets, "choice", _fake_choice)

    assert activation_code_generator.generate_activation_code() == "1234"
