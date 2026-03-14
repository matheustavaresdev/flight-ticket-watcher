"""Tests for browser_profiles module."""

from unittest.mock import patch

from flight_watcher.browser_profiles import (
    BrowserProfile,
    PROFILES,
    get_random_profile,
)


def test_get_random_profile_returns_browser_profile():
    profile = get_random_profile()
    assert isinstance(profile, BrowserProfile)


def test_all_profiles_have_valid_fields():
    for profile in PROFILES:
        assert profile.locale
        assert profile.timezone_id
        assert profile.viewport_width > 0
        assert profile.viewport_height > 0


def test_profiles_contain_expected_viewports():
    widths_heights = {(p.viewport_width, p.viewport_height) for p in PROFILES}
    assert (1920, 1080) in widths_heights
    assert (1366, 768) in widths_heights
    assert (1440, 900) in widths_heights


def test_profiles_contain_expected_locales():
    locales = {p.locale for p in PROFILES}
    assert "pt-BR" in locales
    assert "en-US" in locales


def test_profiles_contain_expected_timezones():
    timezones = {p.timezone_id for p in PROFILES}
    assert "America/Sao_Paulo" in timezones
    assert "America/Fortaleza" in timezones


def test_get_random_profile_uses_random_choice():
    with patch("flight_watcher.browser_profiles.random.choice") as mock_choice:
        mock_choice.return_value = PROFILES[0]
        result = get_random_profile()
        mock_choice.assert_called_once_with(PROFILES)
        assert result == PROFILES[0]
