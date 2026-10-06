"""OdooSupportProvider against the real staging Odoo, as the bridge user.

The bridge has no unlink right on res.partner or helpdesk.ticket (by design),
so the "[TEST] ..." tickets and the @example.invalid contacts these tests
create stay on staging. Contacts are created by the server action (op
"contact"); the bridge itself can only read res.partner.
"""

import json
import os
import uuid
from collections.abc import AsyncIterator

import aiohttp
import pytest
from core.support.errors import SupportCompanyRefused
from core.support.odoo_client import SupportOdooClient
from core.support.odoo_provider import OdooSupportProvider
from core.support.types import NewTicket, TicketQuery, UploadedFile

URL = os.environ.get("ODOO_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        "staging" not in URL or not os.environ.get("ODOO_SUPPORT_API_KEY"),
        reason="needs staging Odoo + bridge key",
    ),
]


@pytest.fixture
async def provider() -> AsyncIterator[OdooSupportProvider]:
    client = SupportOdooClient(
        URL, os.environ["ODOO_DB"], os.environ["ODOO_SUPPORT_API_KEY"]
    )
    yield OdooSupportProvider(
        client,
        team_id=int(os.environ.get("ODOO_SUPPORT_TEAM_ID", "1")),
        post_action_name="GOAT: post message as ticket participant",
    )
    await client.close()


async def test_full_ticket_lifecycle(provider: OdooSupportProvider) -> None:
    email = f"goat-it-{uuid.uuid4().hex[:8]}@example.invalid"
    assert await provider.find_contacts_by_email([email]) == {}
    contact = await provider.create_contact(
        name="GOAT IT Customer", email=email, lang="de", company_id=None
    )
    assert await provider.find_contacts_by_email([email.upper()]) == {email: contact}

    request_id = uuid.uuid4().hex
    ticket = await provider.create_ticket(
        NewTicket(
            subject="[TEST] provider lifecycle",
            description_html="<p>integration</p>",
            category="how_to",
            impact="question",
            customer_contact_id=contact,
            org_id="it-org",
            user_id="it-user",
            request_id=request_id,
        )
    )
    assert ticket.status == "new" and ticket.request_id == request_id

    (again,) = await provider.list_tickets(
        TicketQuery((contact,), contact, None, None, request_id)
    )
    assert again.ref == ticket.ref

    post = await provider.post_message(
        ticket.id,
        contact,
        "Hallo,\n\nzweiter Absatz.",
        [UploadedFile("it.txt", "text/plain", b"hello")],
    )
    assert post.message_id and post.failed_files == ()
    dup = await provider.post_message(
        ticket.id, contact, "Hallo,\n\nzweiter Absatz.", []
    )
    detail = await provider.get_ticket(ticket.ref)
    assert detail is not None
    mine = [m for m in detail.messages if m.author_contact_id == contact]
    assert mine[-1].body_html == "<p>Hallo,</p><p>zweiter Absatz.</p>"
    assert len(detail.visible_attachment_ids) == 1
    assert dup.message_id is not None

    await provider.set_status(ticket.id, "solved")
    await provider.rate(ticket.id, contact, "top", "IT rating")
    await provider.set_status(ticket.id, "in_progress")
    closed = await provider.get_ticket(ticket.ref)
    assert closed is not None and closed.ticket.status == "in_progress"


async def test_duplicate_text_within_a_minute_posts_once(
    provider: OdooSupportProvider,
) -> None:
    email = f"goat-it-{uuid.uuid4().hex[:8]}@example.invalid"
    contact = await provider.create_contact(
        name="GOAT IT Dup", email=email, lang="en", company_id=None
    )
    ticket = await provider.create_ticket(
        NewTicket(
            subject="[TEST] duplicate guard",
            description_html="<p>x</p>",
            category="other",
            impact=None,
            customer_contact_id=contact,
            org_id=None,
            user_id="it",
            request_id=uuid.uuid4().hex,
        )
    )
    # Quotes and an apostrophe: Odoo stores them plain, so this pins that the
    # action escapes only & < > when it compares against the stored body.
    text = 'I\'m "still" here'
    first = await provider.post_message(ticket.id, contact, text, [])
    second = await provider.post_message(ticket.id, contact, text, [])
    assert first.message_id == second.message_id


async def _raw(model: str, method: str, **kw: object) -> int:
    """HTTP status of a JSON-2 call the core client's allow-list would refuse."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{URL.rstrip('/')}/json/2/{model}/{method}",
            data=json.dumps(kw),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"bearer {os.environ['ODOO_SUPPORT_API_KEY']}",
                "X-Odoo-Database": os.environ["ODOO_DB"],
            },
        ) as response:
            return response.status


async def test_contacts_come_from_the_action_only(
    provider: OdooSupportProvider,
) -> None:
    email = f"goat-it-{uuid.uuid4().hex[:8]}@example.invalid"
    odoo = provider._odoo  # noqa: SLF001
    companies = await odoo.call(
        "res.partner",
        "search_read",
        domain=[
            ["is_company", "=", True],
            ["partner_share", "=", True],
            ["ref_company_ids", "=", False],
            ["child_ids", "not any", [["partner_share", "=", False]]],
        ],
        fields=["id"],
        limit=20,
    )
    # The action also refuses companies with former staff in them (archived
    # users or employees, archived contacts too), which this domain cannot see:
    # take the first company it accepts.
    contact = company = None
    for candidate in (c["id"] for c in companies):
        try:
            contact = await provider.create_contact(
                name="GOAT IT Company Contact",
                email=email,
                lang="en",
                company_id=candidate,
            )
        except SupportCompanyRefused:
            continue
        company = candidate
        break
    if contact is None:
        pytest.skip("no customer company without (former) staff on staging")
    (row,) = await odoo.call(
        "res.partner",
        "read",
        ids=[contact],
        fields=["parent_id", "lang", "is_company", "partner_share"],
    )
    assert row["parent_id"][0] == company and row["lang"] == "en_US"
    assert row["is_company"] is False and row["partner_share"] is True
    # own company (a res.company partner) and individuals are no parents
    (own,) = await odoo.call(
        "res.partner",
        "search_read",
        domain=[["ref_company_ids", "!=", False]],
        fields=["id"],
        limit=1,
    )
    for parent in (own["id"], contact):
        with pytest.raises(SupportCompanyRefused):
            await provider.create_contact(
                name="GOAT IT Bad Parent",
                email=f"bad-{email}",
                lang="en",
                company_id=parent,
            )
    # the bridge itself can neither create nor edit contacts
    assert await _raw("res.partner", "create", vals_list=[{"name": "x"}]) == 403
    assert (
        await _raw("res.partner", "write", ids=[contact], vals={"email": "e@x.invalid"})
        == 403
    )


async def test_the_bridge_knows_its_own_partner(
    provider: OdooSupportProvider,
) -> None:
    # find_contacts_by_email excludes this id (unit-tested); on staging the
    # bridge partner has no email, so only the lookup itself is checked here.
    bridge = await provider.bridge_contact_id()
    assert bridge
    (row,) = await provider._odoo.call(  # noqa: SLF001
        "res.partner", "read", ids=[bridge], fields=["name", "partner_share"]
    )
    assert row["name"] == "GOAT Support Bridge" and row["partner_share"] is True
