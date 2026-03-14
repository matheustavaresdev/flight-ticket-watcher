from unittest.mock import patch

import flight_watcher.delays as delays_module


def test_random_delay_sleeps_within_range():
    with (
        patch("flight_watcher.delays.time.sleep") as mock_sleep,
        patch("flight_watcher.delays.random.uniform", return_value=7.5),
    ):
        result = delays_module.random_delay(min_sec=5.0, max_sec=10.0)

    mock_sleep.assert_called_once_with(7.5)
    assert result == 7.5


def test_random_delay_uses_custom_range():
    captured = {}

    def fake_uniform(lo, hi):
        captured["lo"] = lo
        captured["hi"] = hi
        return (lo + hi) / 2

    with (
        patch("flight_watcher.delays.time.sleep"),
        patch("flight_watcher.delays.random.uniform", side_effect=fake_uniform),
    ):
        delays_module.random_delay(min_sec=2.0, max_sec=8.0)

    assert captured["lo"] == 2.0
    assert captured["hi"] == 8.0


def test_random_delay_uses_env_defaults():
    with (
        patch("flight_watcher.delays.time.sleep"),
        patch(
            "flight_watcher.delays.random.uniform", return_value=10.0
        ) as mock_uniform,
        patch.object(delays_module, "MIN_DELAY_SEC", 5.0),
        patch.object(delays_module, "MAX_DELAY_SEC", 15.0),
    ):
        delays_module.random_delay()

    mock_uniform.assert_called_once_with(5.0, 15.0)
