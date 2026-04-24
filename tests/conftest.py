"""Shared fixtures for Conekta plugin tests."""
import pytest

from vbwd.sdk.interface import SDKConfig


@pytest.fixture
def conekta_config() -> dict:
    return {
        "sandbox": True,
        "test_public_key": "key_test_public",
        "test_private_key": "key_test_private_abc",
        "test_api_url": "https://api.conekta.io",
        "api_version": "2.2.0",
        "currency": "MXN",
    }


@pytest.fixture
def sdk_config(conekta_config) -> SDKConfig:
    return SDKConfig(api_key=conekta_config["test_private_key"], sandbox=True)


@pytest.fixture
def adapter(sdk_config, conekta_config):
    from plugins.conekta.conekta.sdk_adapter import ConektaSDKAdapter

    return ConektaSDKAdapter(
        config=sdk_config,
        public_key=conekta_config["test_public_key"],
        api_url=conekta_config["test_api_url"],
        api_version=conekta_config["api_version"],
    )
