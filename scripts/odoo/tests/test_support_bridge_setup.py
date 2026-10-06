"""Dry-run planning is deterministic and the guards hold. Nothing talks to Odoo."""

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import support_bridge_setup as setup  # noqa: E402
from support_bridge_action import (  # noqa: E402
    CONTACT_CHECK_CODE,
    ESCAPE_CODE,
    STAFF_CODE,
    action_code,
)

LAYOUT_IDS = {"mail_notification_layout": 386, "mail_notification_light": 387}
GOAT = "https://goat.example.org"
# The parts of Odoo's layouts the override relies on (cut down from staging, Odoo 19).
LAYOUT_ARCH = """<t t-name="mail.mail_notification_layout">
<html t-att-lang="lang"><body>
<t t-set="subtype_internal" t-value="subtype and subtype.internal"/>
<t t-set="show_header" t-value="email_notification_force_header or has_button_access"/>
<td t-if="has_button_access"><a t-att-href="button_access['url']">View</a></td>
</body></html>
</t>"""


class FakeAdmin:
    def __init__(
        self,
        existing: dict[tuple[str, str], list[int]] | None = None,
        team_name: str = "Customer Care",
        layout_arch: str = LAYOUT_ARCH,
    ) -> None:
        self.team_name = team_name
        self.layout_arch = layout_arch
        self.existing = existing or {}
        self.writes: list[tuple[str, str, dict]] = []

    def call(self, model: str, method: str, **kw: Any) -> Any:
        if model == "helpdesk.team" and method == "search_read":
            return [{"name": self.team_name}]
        if model == "ir.ui.view" and method == "read":
            return [{"id": i, "arch_db": self.layout_arch} for i in kw["ids"]]
        key = (model, str(kw.get("domain")))
        if (
            model == "ir.model.data"
            and method == "search_read"
            and key not in self.existing
        ):
            return [{"res_id": LAYOUT_IDS.get(kw["domain"][1][2], 99)}]
        if method in ("search", "search_read"):
            return self.existing.get((model, str(kw.get("domain"))), [])
        self.writes.append((model, method, kw))
        return [1]


def test_refuses_production_without_the_flag() -> None:
    with pytest.raises(SystemExit):
        setup.guard_target(
            "https://odoo.example.org",
            "odoo-main",
            production=False,
        )
    setup.guard_target(
        "https://odoo-staging.example.org",
        "odoo-staging",
        production=False,
    )
    setup.guard_target("https://odoo.example.org", "odoo-main", production=True)


def test_plan_lists_every_verified_right_and_never_delete_on_tickets() -> None:
    steps = setup.plan(FakeAdmin(), team_id=1, goat_url="https://goat.example.org")
    access = {s.detail["model"]: s.detail for s in steps if s.kind == "access"}
    assert access["helpdesk.ticket"]["perm_unlink"] is False
    assert access["res.partner"]["perm_unlink"] is False
    assert access["mail.followers"]["perm_unlink"] is False
    assert {
        "res.partner.category",
        "mail.compose.message",
        "mail.template",
        "ir.actions.server",
    } <= set(access)
    kinds = [s.kind for s in steps]
    assert kinds.count("field") == 3  # organization, user, request id
    assert "server_action" in kinds and "template_patch" in kinds and "user" in kinds


def test_action_code_embeds_group_and_team_and_guards() -> None:
    code = action_code(group_id=160, team_id=1)
    assert "160 not in env.user.all_group_ids.ids" in code
    assert "author.partner_share" in code  # staff followers cannot be impersonated
    assert "staff_ids(author.ids)" in code  # nor former staff (archived/deleted user)
    assert "ticket.team_id.id != 1" in code
    assert "author not in participants" in code
    assert "root = env.ref('base.user_root')" in code
    assert "ticket.with_user(root).with_context(clean).message_post(" in code
    assert "timedelta(seconds=60)" in code  # duplicate guard
    assert "goat_op" in code and "rating.rating" in code
    assert "with_context(clean)" in code
    # the bridge (portal) cannot read res.users, so an assigned agent must be read as root
    assert "ticket.sudo().user_id.partner_id.id" in code
    compile(code, "<action>", "exec")  # valid Python


def test_template_patch_is_idempotent() -> None:
    body = '<a t-att-href="object.get_portal_url()" target="_blank">Ticket ansehen</a>'
    patched = setup.patch_template_body(body, "https://goat.example.org")
    assert "object.x_goat_user_id or object.x_goat_organization_id" in patched
    assert "https://goat.example.org/support/" in patched
    assert setup.patch_template_body(patched, "https://goat.example.org") == patched


def test_plan_refuses_a_team_that_is_not_customer_care() -> None:
    with pytest.raises(SystemExit, match="Sales"):
        setup.plan(
            FakeAdmin(team_name="Sales"),
            team_id=2,
            goat_url="https://goat.example.org",
        )
    steps = setup.plan(FakeAdmin(), team_id=1, goat_url="https://goat.example.org")
    assert steps[0].kind == "team" and "Customer Care" in steps[0].description


def test_bridge_cannot_create_delete_followers_or_write_ratings_and_messages() -> None:
    for model in ("mail.followers", "rating.rating", "mail.message"):
        assert setup.ACCESS[model] == (True, False, False, False), model
    for name, model, _domain, _r, w, c, u in setup.RULES:
        if model in ("mail.followers", "rating.rating", "mail.message"):
            assert not (w or c or u), name


def test_escape_code_escapes_markup_but_not_quotes() -> None:
    namespace: dict[str, Any] = {"body": 'I\'m "here" & <b>\nx'}
    exec(ESCAPE_CODE, namespace)
    assert namespace["html"] == '<p>I\'m "here" &amp; &lt;b&gt;<br>x</p>'
    namespace = {"body": "a\r\n\r\nb\nc\n\n\n"}
    exec(ESCAPE_CODE, namespace)
    assert namespace["html"] == "<p>a</p><p>b<br>c</p>"
    assert ESCAPE_CODE.strip() in action_code(1, 1).replace("\n    ", "\n")


def test_template_patch_fails_loudly_and_repoints() -> None:
    with pytest.raises(ValueError, match="nothing to patch"):
        setup.patch_template_body("<a href='/x'>hi</a>", "https://goat.example.org")
    with pytest.raises(ValueError, match="expected button link"):
        setup.patch_template_body(
            "<a>x_goat_organization_id</a>", "https://goat.example.org"
        )
    body = '<a t-att-href="object.get_portal_url()">x</a>'
    old = setup.patch_template_body(body, "https://old.example")
    new = setup.patch_template_body(old, "https://goat.example.org/")
    assert "old.example" not in new
    assert "https://goat.example.org/support/%s" in new
    assert new.count("get_portal_url()") == 1


def test_missing_template_is_a_clear_error() -> None:
    with pytest.raises(SystemExit, match="not found"):
        setup._patch_template(FakeAdmin(), "Helpdesk: Nope", "https://goat.example.org")


def test_final_rights_are_the_proven_minimum() -> None:
    a = setup.ACCESS
    # read only: contacts are created by the server action (op "contact")
    assert a["res.partner"] == (True, False, False, False)
    assert a["ir.attachment"] == (True, False, True, False)  # upload + read only
    assert a["mail.compose.message"] == (
        False,
        False,
        True,
        False,
    )  # ticket-create mail
    assert "mail.mail" not in a
    assert "mail.mail" in setup.LEGACY_ACCESS
    for name, model, _d, r, w, c, u in setup.RULES:
        if model == "ir.attachment":
            assert not (w or u), name
        if model == "res.partner":
            assert not (w or c or u), name
    assert not any(model == "mail.mail" for _n, model, *_ in setup.RULES)
    assert any(n == "goat bridge: own mails only" for n, _m in setup.LEGACY_RULES)


def test_plan_removes_legacy_rows_only_when_they_exist() -> None:
    steps = setup.plan(FakeAdmin(), team_id=1, goat_url="https://goat.example.org")
    assert not [s for s in steps if s.kind.startswith("remove_")]
    existing = {
        ("ir.model.access", str([["name", "=", "goat bridge: mail.mail"]])): [5],
        ("ir.rule", str([["name", "=", "goat bridge: own mails only"]])): [6],
    }
    steps = setup.plan(
        FakeAdmin(existing), team_id=1, goat_url="https://goat.example.org"
    )
    assert [s.kind for s in steps if s.kind.startswith("remove_")] == [
        "remove_access",
        "remove_rule",
    ]


@pytest.mark.parametrize(
    "url",
    [
        "https://goat.example.org",
        "https://goat.example.org/",
        "https://goat-dev.example.com:8443/app",
        "http://localhost:3000",
        "http://127.0.0.1",
    ],
)
def test_goat_url_accepts_plain_urls(url: str) -> None:
    assert setup.validate_goat_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://goat.example.org",
        "ftp://goat.example.com",
        "https://goat.example.com'",
        'https://goat.example.com"x',
        "https://goat.example.com/a b",
        "https://goat.example.com/<script>",
        "https://goat.example.com\n",
        "javascript:alert(1)",
        "http://localhost.evil.com",
        "",
    ],
)
def test_goat_url_rejects_anything_that_could_break_the_template(url: str) -> None:
    with pytest.raises(SystemExit):
        setup.validate_goat_url(url)
    with pytest.raises(SystemExit):
        setup.plan(FakeAdmin(), team_id=1, goat_url=url)


def test_close_button_is_hidden_for_goat_tickets_idempotently() -> None:
    body = (
        '<t t-if="object.team_id.allow_portal_ticket_closing"><td>'
        "<a t-att-href=\"'/my/ticket/close/%s/%s' % (object.id, object.access_token)\">x</a>"
        "</td></t>"
    )
    patched = setup.hide_close_button_for_goat_tickets(body)
    assert "and not (object.x_goat_user_id or" in patched
    assert setup.hide_close_button_for_goat_tickets(patched) == patched
    # a template without the button is left alone
    assert setup.hide_close_button_for_goat_tickets("<p>x</p>") == "<p>x</p>"
    # a button in an unknown wrapper fails loudly
    with pytest.raises(ValueError, match="close-ticket button"):
        setup.hide_close_button_for_goat_tickets('<a href="/my/ticket/close/1/2">x</a>')


def test_client_defaults_every_call_to_the_source_language(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    sent: list[dict] = []

    class Resp:
        def __enter__(self) -> "Resp":
            return self

        def __exit__(self, *a: object) -> None:
            return None

        def read(self) -> bytes:
            return b"[]"

    def fake_urlopen(req, timeout):  # type: ignore[no-untyped-def]
        sent.append(__import__("json").loads(req.data))
        return Resp()

    monkeypatch.setattr(setup.urllib.request, "urlopen", fake_urlopen)
    client = setup.Odoo("https://odoo-staging.example.org", "db", "k")
    client.call("mail.template", "search", domain=[["name", "=", "n"]])
    client.call("mail.template", "read", ids=[1], context={"lang": "de_DE", "a": 1})
    assert sent[0]["context"] == {"lang": "en_US"}
    assert sent[1]["context"] == {"lang": "de_DE", "a": 1}


def test_dry_run_shows_the_formatted_rule_domains() -> None:
    steps = setup.plan(FakeAdmin(), team_id=1, goat_url="https://goat.example.org")
    text = "\n".join(s.description for s in steps)
    assert "{" not in text.replace("{}", "")
    assert "('team_id', '=', 1)" in text


def test_round_two_patched_templates_migrate_to_the_user_id_condition() -> None:
    old_href = (
        "<a t-att-href=\"('https://goat.example.org/support/%s' % object.ticket_ref) "
        'if object.x_goat_organization_id else object.get_portal_url()">x</a>'
    )
    new = setup.patch_template_body(old_href, "https://goat.example.org")
    assert "object.x_goat_user_id" in new
    assert "if object.x_goat_organization_id else" not in new
    assert setup.patch_template_body(new, "https://goat.example.org") == new
    old_close = (
        '<t t-if="object.team_id.allow_portal_ticket_closing '
        'and not object.x_goat_organization_id"><a href="/my/ticket/close/1">x</a></t>'
    )
    migrated = setup.hide_close_button_for_goat_tickets(old_close)
    assert "x_goat_user_id" in migrated
    assert setup.hide_close_button_for_goat_tickets(migrated) == migrated


def test_goat_link_does_not_need_an_organization() -> None:
    patched = setup.patch_template_body(
        '<a t-att-href="object.get_portal_url()">x</a>', "https://goat.example.org"
    )
    # /support/<ref> only; the condition is true when only x_goat_user_id is set
    assert "/support/%s' % object.ticket_ref" in patched
    assert "org" not in patched.split("/support/")[1].split("if ")[0]


def test_old_partner_create_and_edit_rules_are_removed_on_re_run() -> None:
    names = {n for n, m in setup.LEGACY_RULES if m == "res.partner"}
    assert names >= {
        "goat bridge: create individuals only",
        "goat bridge: edit customer contacts only",
    }
    assert not names & {n for n, *_ in setup.RULES}
    existing = {
        ("ir.rule", str([["name", "=", name]])): [7 + i]
        for i, name in enumerate(sorted(names))
    }
    steps = setup.plan(
        FakeAdmin(existing), team_id=1, goat_url="https://goat.example.org"
    )
    removed = [s.detail["name"] for s in steps if s.kind == "remove_rule"]
    assert sorted(removed) == sorted(names)


def test_contact_op_creates_individuals_only_as_root_with_a_clean_context() -> None:
    code = action_code(group_id=160, team_id=1)
    contact = code.split("if op == 'contact':")[1].split("elif op not in")[0]
    # the group check comes first, before any op (no ticket needed for "contact")
    assert code.index("160 not in env.user.all_group_ids.ids") < code.index(
        "if op == 'contact':"
    )
    assert "'is_company': False" in contact
    assert (
        "env['res.partner'].with_user(root).with_context(clean).create(vals)" in contact
    )
    assert "lang not in ('en_US', 'de_DE')" in contact
    # the parent must be a customer company: not ours, nobody internal in it
    assert "not parent.is_company" in contact
    assert "parent.ref_company_ids" in contact
    assert "staff_ids(partners.search([('id', 'child_of', parent.id)]).ids)" in contact
    assert "'goat_contact_id': contact.id" in contact
    # ticket ops keep their guards
    rest = code.split("elif op not in ('rate', 'post'):")[1]
    assert "ticket.team_id.id != 1" in rest and "author not in participants" in rest


def _layout_steps(client: FakeAdmin, goat_url: str = GOAT) -> list[setup.Step]:
    return [
        s
        for s in setup.plan(client, team_id=1, goat_url=goat_url)
        if s.kind == "layout_view"
    ]


def _existing_view(name: str, parent_id: int, arch: str, view_id: int) -> dict:
    domain = [
        ["name", "=", name],
        ["inherit_id", "=", parent_id],
        ["active", "in", [True, False]],
    ]
    return {
        ("ir.ui.view", str(domain)): [{"id": view_id, "arch_db": arch, "active": True}]
    }


def test_plan_creates_one_inherited_view_per_notification_layout() -> None:
    steps = _layout_steps(FakeAdmin())
    assert [(s.detail["layout"], s.detail["action"]) for s in steps] == [
        ("mail.mail_notification_layout", "create"),
        ("mail.mail_notification_light", "create"),
    ]
    assert [s.detail["parent_id"] for s in steps] == [386, 387]
    assert all(
        s.detail["name"].startswith("GOAT: support reply links to GOAT") for s in steps
    )
    # deterministic: same input, same plan
    again = _layout_steps(FakeAdmin())
    assert [(s.description, s.detail) for s in steps] == [
        (s.description, s.detail) for s in again
    ]


def test_layout_view_arch_sets_the_goat_button_before_the_header_is_computed() -> None:
    import xml.etree.ElementTree as ET

    arch = setup.layout_view_arch(GOAT + "/")
    root = ET.fromstring(arch)  # well-formed
    (xpath,) = root
    # structural: the first element in the template, before anything is computed
    assert xpath.get("expr") == "/*/*[1]"
    assert xpath.get("position") == "before"
    assert "recipients_data is not None" in xpath[0].get("t-if")
    cond = xpath[0].get("t-if")
    assert "record._name == 'helpdesk.ticket'" in cond
    assert "(record.x_goat_user_id or record.x_goat_organization_id)" in cond
    assert "r.get('type') == 'user'" in cond  # internal recipients keep the Odoo link
    set_button, set_has = xpath[0]
    assert set_button.get("t-set") == "button_access"
    assert (
        "url='https://goat.example.org/support/%s' % record.ticket_ref"
        in set_button.get("t-value")
    )
    assert (set_has.get("t-set"), set_has.get("t-value")) == (
        "has_button_access",
        "True",
    )
    assert "//support" not in arch


class _Ticket:
    def __init__(self, name: str = "helpdesk.ticket", goat: bool = True) -> None:
        self._name = name
        self.x_goat_user_id = "u-1" if goat else False
        self.x_goat_organization_id = False
        self.ticket_ref = "00064"

    def __bool__(self) -> bool:
        return True


def _render(arch: str, **values: Any) -> dict:
    """Evaluate the view's t-if / t-set like QWeb does, on a copy of the values."""
    import xml.etree.ElementTree as ET

    (xpath,) = ET.fromstring(arch)
    (block,) = xpath
    values = {"recipients_data": [], "model_description": "Ticket", **values}
    values.setdefault("record_name", "x")
    if eval(block.get("t-if"), {}, dict(values)):
        for tset in block:
            values[tset.get("t-set")] = eval(tset.get("t-value"), {}, dict(values))
    return values


def test_layout_view_behaviour_per_recipient_group() -> None:
    arch = setup.layout_view_arch(GOAT)
    goat_url = "https://goat.example.org/support/00064"
    odoo = {
        "url": "https://odoo/mail/view?res_id=64",
        "title": "Kundendienstticket ansehen",
    }
    customer = [{"type": "customer", "share": True}]
    # the ticket's customer: Odoo's button, re-pointed, title kept
    out = _render(
        arch,
        record=_Ticket(),
        has_button_access=True,
        button_access=odoo,
        recipients_data=[{"type": "portal"}],
    )
    assert out["button_access"] == {"url": goat_url, "title": odoo["title"]}
    # a colleague following the ticket without a user: Odoo shows no button, GOAT adds it
    out = _render(
        arch,
        record=_Ticket(),
        has_button_access=False,
        button_access=odoo,
        recipients_data=customer,
    )
    assert out["has_button_access"] is True
    assert out["button_access"] == {"url": goat_url, "title": odoo["title"]}
    # internal staff, other tickets, other models: untouched
    for record, data in [
        (_Ticket(), [{"type": "user"}]),
        (_Ticket(), customer + [{"type": "user"}]),
        (_Ticket(goat=False), customer),
        (_Ticket(name="sale.order"), customer),
        (_Ticket(), None),  # rendered without recipient groups: Odoo's link
    ]:
        out = _render(
            arch,
            record=record,
            has_button_access=False,
            button_access=odoo,
            recipients_data=data,
        )
        assert out["has_button_access"] is False and out["button_access"] is odoo


def test_layout_view_uses_the_validated_goat_url() -> None:
    steps = _layout_steps(FakeAdmin(), "https://goat-dev.example.com:8443/app")
    assert all(
        "'https://goat-dev.example.com:8443/app/support/%s'" in s.detail["arch"]
        for s in steps
    )
    with pytest.raises(SystemExit):
        _layout_steps(FakeAdmin(), "https://x.example.com' or 1 or '")


def test_layout_view_already_present_is_kept_and_not_written() -> None:
    arch = setup.layout_view_arch(GOAT)
    existing = {
        **_existing_view(
            "GOAT: support reply links to GOAT", 386, arch + "\n", view_id=501
        ),
        **_existing_view(
            "GOAT: support reply links to GOAT (light layout)", 387, arch, view_id=502
        ),
    }
    client = FakeAdmin(existing)
    steps = _layout_steps(client)
    assert [s.detail["action"] for s in steps] == ["keep", "keep"]
    assert all(s.description.startswith("up to date:") for s in steps)
    for s in steps:
        setup._apply_layout_view(client, s.detail)
    assert client.writes == []


def test_layout_view_with_an_old_url_is_updated_in_place_never_the_base_layout() -> (
    None
):
    old = setup.layout_view_arch("https://old.example")
    client = FakeAdmin(
        _existing_view("GOAT: support reply links to GOAT", 386, old, view_id=501)
    )
    steps = _layout_steps(client)
    assert [s.detail["action"] for s in steps] == ["update", "create"]
    for s in steps:
        setup._apply_layout_view(client, s.detail)
    write, create = client.writes
    assert write[:2] == ("ir.ui.view", "write") and write[2]["ids"] == [501]
    assert "https://goat.example.org/support/" in write[2]["vals"]["arch"]
    assert create[:2] == ("ir.ui.view", "create")
    (vals,) = create[2]["vals_list"]
    assert vals["mode"] == "extension" and vals["inherit_id"] == 387
    assert vals["type"] == "qweb"
    # Odoo's own layouts (386, 387) are only ever the parent, never written
    assert not any(
        m == "ir.ui.view" and kw.get("ids") in ([386], [387])
        for m, _meth, kw in client.writes
    )


def test_missing_notification_layout_is_a_clear_error() -> None:
    domain = [
        ["module", "=", "mail"],
        ["name", "=", "mail_notification_layout"],
        ["model", "=", "ir.ui.view"],
    ]
    client = FakeAdmin({("ir.model.data", str(domain)): []})
    with pytest.raises(SystemExit, match="mail.mail_notification_layout not found"):
        setup.plan(client, team_id=1, goat_url=GOAT)


# ---------------------------------------------------------------- staff_ids
class _Recs:
    """Just enough of an Odoo recordset for STAFF_CODE."""

    def __init__(self, items: list[Any]) -> None:
        self.items = items

    @property
    def ids(self) -> list[int]:
        return [r.id for r in self.items]

    def filtered(self, fn: Any) -> "_Recs":
        return _Recs([r for r in self.items if fn(r)])

    def mapped(self, name: str) -> "_Recs":
        return _Recs([getattr(r, name) for r in self.items if getattr(r, name)])

    def exists(self) -> "_Recs":
        return self


class _Rec:
    def __init__(self, id: int, **kw: Any) -> None:
        self.id = id
        self.__dict__.update(kw)


class _Model:
    def __init__(self, env: "_Env", name: str) -> None:
        self.env, self.name = env, name

    def sudo(self) -> "_Model":
        return self

    def with_context(self, **ctx: Any) -> "_Model":
        self.env.contexts.append((self.name, ctx))
        return self

    def browse(self, ids: list[int]) -> _Recs:
        return _Recs([p for p in self.env.partners if p.id in ids])

    def search(self, domain: list) -> _Recs:
        ((field, op, ids),) = domain
        assert (field, op) == ("work_contact_id", "in")
        return _Recs(
            [
                e
                for e in self.env.employees
                if getattr(e.work_contact_id, "id", 0) in ids
            ]
        )


class _Env:
    def __init__(self, partners: list[_Rec], employees: list[_Rec] | None) -> None:
        self.partners = partners
        self.employees = employees or []
        self.has_hr = employees is not None
        self.contexts: list[tuple[str, dict]] = []

    def __contains__(self, model: str) -> bool:
        return model == "hr.employee" and self.has_hr

    def __getitem__(self, model: str) -> _Model:
        return _Model(self, model)


def _staff_ids(env: _Env, ids: list[int]) -> set[int]:
    namespace: dict[str, Any] = {"env": env}
    exec(STAFF_CODE, namespace)
    return namespace["staff_ids"](ids)


def _user(share: bool) -> _Rec:
    return _Rec(0, share=share)


def test_staff_are_current_and_former_staff_of_any_kind() -> None:
    active_staff = _Rec(1, partner_share=False, user_ids=[_user(False)])
    # Odoo recomputes partner_share from active users only: archived staff turns "share"
    archived_staff = _Rec(2, partner_share=True, user_ids=[_user(False)])
    # user deleted, the (archived) employee record is left
    deleted_user = _Rec(3, partner_share=True, user_ids=[])
    customer = _Rec(4, partner_share=True, user_ids=[])
    portal = _Rec(5, partner_share=True, user_ids=[_user(True)])
    env = _Env(
        [active_staff, archived_staff, deleted_user, customer, portal],
        [_Rec(90, work_contact_id=deleted_user), _Rec(91, work_contact_id=False)],
    )
    assert _staff_ids(env, [1, 2, 3, 4, 5, 6]) == {1, 2, 3}
    # archived users and archived employees count: both lookups see inactive records
    assert ("res.partner", {"active_test": False}) in env.contexts
    assert ("hr.employee", {"active_test": False}) in env.contexts


def test_staff_without_the_hr_module_are_judged_by_their_users() -> None:
    env = _Env(
        [
            _Rec(2, partner_share=True, user_ids=[_user(False)]),
            _Rec(3, partner_share=True, user_ids=[]),
        ],
        None,
    )
    assert _staff_ids(env, ["2", 3]) == {2}


def test_staff_op_answers_ids_and_caps_the_batch() -> None:
    code = action_code(group_id=160, team_id=1)
    staff = code.split("elif op == 'staff':")[1].split("elif op not in")[0]
    assert "len(ids) > 1000" in staff
    assert "'goat_staff_ids': sorted(staff_ids(ids))" in staff
    # defined once, before any op, after the group check
    assert code.index("160 not in env.user.all_group_ids.ids") < code.index(
        "def staff_ids(ids):"
    )
    assert code.index("def staff_ids(ids):") < code.index("if op == 'contact':")
    assert STAFF_CODE in code


# ----------------------------------------------------------------- agent op
class _UserError(Exception):
    pass


def _run_agent_op(ticket: Any, groups: list[int] | None = None) -> dict:
    """Runs the action code's "agent" op against a fake env, as Odoo's safe_eval would."""
    from unittest.mock import MagicMock

    env = MagicMock()
    env.user.all_group_ids.ids = [160] if groups is None else groups
    env.context = {"goat_op": "agent", "active_id": 31}
    tickets = MagicMock()
    tickets.browse.return_value.exists.return_value = ticket
    env.__getitem__.side_effect = lambda name: {"helpdesk.ticket": tickets}[name]
    namespace: dict[str, Any] = {"env": env, "UserError": _UserError, "log": print}
    exec(action_code(group_id=160, team_id=1), namespace)
    return namespace["action"]


def _agent_ticket(team_id: int, partner_id: int | None) -> Any:
    from unittest.mock import MagicMock

    ticket = MagicMock()
    ticket.team_id.id = team_id
    ticket.sudo.return_value.user_id.partner_id.id = partner_id
    return ticket


def test_agent_op_answers_the_assigned_agents_partner() -> None:
    action = _run_agent_op(_agent_ticket(1, 777))
    assert action["goat_agent_partner_id"] == 777


def test_agent_op_answers_false_for_an_unassigned_ticket() -> None:
    action = _run_agent_op(_agent_ticket(1, None))
    assert action["goat_agent_partner_id"] is False


def test_agent_op_keeps_the_group_and_team_guards() -> None:
    with pytest.raises(_UserError, match="not allowed"):
        _run_agent_op(_agent_ticket(1, 777), groups=[1])
    with pytest.raises(_UserError, match="unknown ticket"):
        _run_agent_op(_agent_ticket(2, 777))  # another team's ticket
    with pytest.raises(_UserError, match="unknown ticket"):
        _run_agent_op(None)  # no such ticket


def test_agent_op_is_read_only_and_never_acts_as_root() -> None:
    code = action_code(group_id=160, team_id=1)
    agent = code.split("elif op == 'agent':")[1].split("elif op not in")[0]
    assert "goat_agent_partner_id" in agent
    for forbidden in ("create(", "write(", "with_user(root)", "message_post"):
        assert forbidden not in agent


# --------------------------------------------------------------- contact op
def _contact_error(name: str, email: str) -> str | None:
    namespace: dict[str, Any] = {}
    exec(CONTACT_CHECK_CODE, namespace)
    return namespace["contact_input_error"](name, email)


@pytest.mark.parametrize(
    "email",
    [
        "anna@stadt.de",
        "a.b+c@sub.x-y.de",
        "o'neil@example.invalid",
        "x!#$%&*/=?^_`{|}~-@x.de",
    ],
)
def test_contact_input_accepts_plain_addresses(email: str) -> None:
    assert _contact_error("Anna Keller", email) is None


@pytest.mark.parametrize(
    "email",
    [
        "a@x",  # no dot in the domain
        "a..b@x.de",
        ".a@x.de",
        "a.@x.de",
        "a@-x.de",
        "a@x-.de",
        "a@x..de",
        "a b@x.de",
        "a<b@x.de",
        "a,b@x.de",
        "a@b@x.de",
        "ä@x.de",
        "a@x.de\r",
        "a@x.de\nBcc: b@y.de",
        "a\t@x.de",
        "@x.de",
        "a@",
        "x" * 65 + "@x.de",
    ],
)
def test_contact_input_refuses_anything_else_as_email(email: str) -> None:
    assert _contact_error("Anna", email) == "invalid contact"


@pytest.mark.parametrize(
    "name", ["", "Anna\nKeller", "Anna\r", "A\tB", "A\x7f", "A\x85", "x" * 201]
)
def test_contact_input_refuses_control_characters_and_long_names(name: str) -> None:
    assert _contact_error(name, "anna@stadt.de") == "invalid contact"


class _Partners:
    """res.partner for the contact op: search by email, browse for staff_ids, create."""

    def __init__(self, env: "_ContactEnv") -> None:
        self.env = env

    def sudo(self) -> "_Partners":
        return self

    def with_context(self, *args: Any, **ctx: Any) -> "_Partners":
        return self

    def with_user(self, user: Any) -> "_Partners":
        return self

    def search(self, domain: list) -> _Recs:
        ((field, op, value),) = domain
        assert (field, op) == ("email_normalized", "=")
        return _Recs([p for p in self.env.partners if p.email == value])

    def browse(self, ids: list[int]) -> _Recs:
        return _Recs([p for p in self.env.partners if p.id in ids])

    def create(self, vals: dict) -> _Rec:
        self.env.created.append(vals)
        return _Rec(4242)


class _ContactEnv:
    def __init__(self, partners: list[_Rec], context: dict) -> None:
        from unittest.mock import MagicMock

        self.partners = partners
        self.created: list[dict] = []
        self.context = context
        self.user = MagicMock()
        self.user.all_group_ids.ids = [160]

    def ref(self, xmlid: str) -> str:
        return xmlid

    def __contains__(self, model: str) -> bool:
        return False  # no hr module: staff = internal users

    def __getitem__(self, model: str) -> _Partners:
        assert model == "res.partner"
        return _Partners(self)


def _run_contact_op(env: _ContactEnv) -> dict:
    namespace: dict[str, Any] = {"env": env, "UserError": _UserError, "log": print}
    exec(action_code(group_id=160, team_id=1), namespace)
    return namespace["action"]


def _contact_ctx(email: str, name: str = "Anna Keller") -> dict:
    return {
        "goat_op": "contact",
        "goat_name": name,
        "goat_email": email,
        "goat_lang": "de_DE",
    }


def test_contact_op_creates_a_contact_for_a_customer_email() -> None:
    customer = _Rec(1, email="anna@stadt.de", partner_share=True, user_ids=[])
    env = _ContactEnv([customer], _contact_ctx("Anna@Stadt.de"))
    assert _run_contact_op(env)["goat_contact_id"] == 4242
    (vals,) = env.created
    assert (vals["email"], vals["lang"], vals["is_company"]) == (
        "Anna@Stadt.de",
        "de_DE",
        False,
    )


def test_contact_op_refuses_the_email_of_staff_and_former_staff() -> None:
    staff = _Rec(
        1, email="lena@example.org", partner_share=False, user_ids=[_user(False)]
    )
    archived = _Rec(
        2, email="old@example.org", partner_share=True, user_ids=[_user(False)]
    )
    for email in ("Lena@example.org", "old@example.org"):
        env = _ContactEnv([staff, archived], _contact_ctx(email))
        with pytest.raises(_UserError, match="email belongs to staff"):
            _run_contact_op(env)
        assert env.created == []


def test_contact_op_refuses_odd_input_before_looking_anything_up() -> None:
    env = _ContactEnv([], _contact_ctx("anna@stadt.de\r\nBcc: x@y.de"))
    with pytest.raises(_UserError, match="invalid contact"):
        _run_contact_op(env)
    env = _ContactEnv([], _contact_ctx("anna@stadt.de", name="Anna\nKeller"))
    with pytest.raises(_UserError, match="invalid contact"):
        _run_contact_op(env)
    assert env.created == []


def test_layout_anchor_matches_before_everything_the_real_layouts_compute() -> None:
    import xml.etree.ElementTree as ET

    for arch in (LAYOUT_ARCH, LAYOUT_ARCH.replace("subtype_internal", "renamed")):
        root = ET.fromstring(arch)
        # /*/*[1]: the root's first element child
        first = root[0]
        assert "show_header" in ET.tostring(first, encoding="unicode")
        assert setup.layout_assumptions_missing(arch) == []


@pytest.mark.parametrize(
    ("arch", "missing"),
    [
        (LAYOUT_ARCH.replace("has_button_access", "has_link"), ["has_button_access"]),
        (
            LAYOUT_ARCH.replace("button_access['url']", "link_url"),
            ["button_access['url']"],
        ),
        (
            "<t t-name=\"x\">has_button_access button_access['url']</t>",
            ["a first element"],
        ),
    ],
)
def test_plan_checks_what_the_layout_override_relies_on(
    arch: str, missing: list[str]
) -> None:
    assert setup.layout_assumptions_missing(arch) == missing


def test_a_layout_that_changed_under_us_deactivates_our_view_instead_of_breaking_mail() -> (
    None
):
    changed = LAYOUT_ARCH.replace("has_button_access", "has_link")
    existing = _existing_view(
        "GOAT: support reply links to GOAT",
        386,
        setup.layout_view_arch(GOAT),
        view_id=501,
    )
    client = FakeAdmin(existing, layout_arch=changed)
    steps = _layout_steps(client)
    assert [s.detail["action"] for s in steps] == ["deactivate", "skip"]
    assert all(s.description.startswith("WARNING") for s in steps)
    for s in steps:
        setup._apply_layout_view(client, s.detail)
    assert client.writes == [
        ("ir.ui.view", "write", {"ids": [501], "vals": {"active": False}})
    ]


def test_action_code_has_no_closures_odoo_safe_eval_refuses() -> None:
    import dis
    import types

    forbidden = {"LOAD_CLOSURE", "STORE_DEREF", "LOAD_DEREF", "MAKE_CELL"}

    def opcodes(code: types.CodeType) -> set[str]:
        found = {i.opname for i in dis.get_instructions(code)}
        for const in code.co_consts:
            if isinstance(const, types.CodeType):
                found |= opcodes(const)
        return found

    code = compile(action_code(group_id=160, team_id=1), "<server action>", "exec")
    assert opcodes(code) & forbidden == set()
