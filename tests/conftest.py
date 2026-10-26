import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def no_api_spacing(monkeypatch):
    """No waiting between automatic API calls in tests (the default is a few seconds)."""
    from custom_components.enbw_laadpalen import const

    monkeypatch.setattr(const, "DEFAULT_API_SPACING", 0.0)
