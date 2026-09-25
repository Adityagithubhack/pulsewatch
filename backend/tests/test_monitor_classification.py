from app.services.monitor import classify_response


def test_expected_response_is_up() -> None:
    assert classify_response(204, 204) == ("up", None)


def test_access_control_responses_are_blocked() -> None:
    assert classify_response(403, 200)[0] == "blocked"
    assert classify_response(429, 200)[0] == "blocked"


def test_unexpected_response_is_down() -> None:
    availability, error = classify_response(503, 200)
    assert availability == "down"
    assert error == "Expected 200, received 503"
