from app.services.auth import hash_password, token_digest, verify_password


def test_password_hash_round_trip() -> None:
    encoded = hash_password("correct-horse-battery-staple")
    assert encoded.startswith("scrypt$")
    assert verify_password("correct-horse-battery-staple", encoded)
    assert not verify_password("wrong-password", encoded)


def test_session_tokens_are_not_stored_raw() -> None:
    token = "private-session-token"
    assert token_digest(token) != token
    assert len(token_digest(token)) == 64
