import pytest
from core.services.provisioner import (
    FakeProvisioner,
    slugify_domain,
)


def test_slugify_domain_simple() -> None:
    assert slugify_domain("klima.example.com") == "cd-klima-example-com"


def test_slugify_domain_lowercases() -> None:
    assert slugify_domain("Klima.EXAMPLE.com") == "cd-klima-example-com"


@pytest.mark.asyncio
async def test_fake_provision_records_domain() -> None:
    fake = FakeProvisioner()
    await fake.provision(base_domain="klima.example.com")
    assert "klima.example.com" in fake.created


@pytest.mark.asyncio
async def test_fake_provision_is_idempotent() -> None:
    fake = FakeProvisioner()
    await fake.provision(base_domain="klima.example.com")
    await fake.provision(base_domain="klima.example.com")
    # Only one entry, even after two calls.
    assert fake.created == ["klima.example.com"]


@pytest.mark.asyncio
async def test_fake_release_removes_record() -> None:
    fake = FakeProvisioner()
    await fake.provision(base_domain="klima.example.com")
    await fake.release(base_domain="klima.example.com")
    assert "klima.example.com" not in fake.created


@pytest.mark.asyncio
async def test_fake_release_is_idempotent() -> None:
    fake = FakeProvisioner()
    # Releasing before provisioning should not error.
    await fake.release(base_domain="klima.example.com")
    assert fake.created == []
