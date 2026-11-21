import pytest

from rhinos_buddy import i18n


@pytest.fixture(autouse=True)
def _reset_language():
    """The interface language is a process-wide setting: every test starts (and ends) in Portuguese."""
    i18n.set_lang("pt")
    yield
    i18n.set_lang("pt")
