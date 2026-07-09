import pytest

from stepcheck_providers import available_providers, create_provider
from stepcheck_providers.base import VisionProvider
from stepcheck_providers.registry import register_provider


def test_builtin_providers_registered():
    names = available_providers()
    assert "mock" in names
    assert "openai" in names


def test_create_unknown_provider_raises():
    with pytest.raises(KeyError):
        create_provider("does-not-exist")


def test_register_and_create_custom_provider():
    @register_provider("custom-test")
    class _Custom(VisionProvider):
        async def verify(self, request):
            return []

    provider = create_provider("custom-test")
    assert isinstance(provider, VisionProvider)
    assert provider.name == "custom-test"


def test_duplicate_registration_raises():
    with pytest.raises(ValueError):

        @register_provider("mock")
        class _Dupe(VisionProvider):
            async def verify(self, request):
                return []
