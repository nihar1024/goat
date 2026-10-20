"""Unit tests for the Odoo -> GOAT entitlement computation (pure part)."""

from goatlib.tasks.odoo_entitlement import compute_entitlement


def order(**overrides) -> dict:
    base = {
        "subscription_state": "3_progress",
        "next_invoice_date": "2026-08-01",
        "x_goat_organization_id": "b65e040a-f8f0-453f-9888-baa2b9342cce",
        "x_goat_editors": 0,
        "x_goat_viewers": 0,
        "x_goat_projects": 0,
        "x_goat_storage_mb": 0,
        "x_goat_white_label": False,
    }
    base.update(overrides)
    return base


BASE_LINE = {  # the GOAT base product carries the floor on its own line
    "qty": 1.0,
    "x_goat_editors": 3,
    "x_goat_viewers": 2,
    "x_goat_projects": 50,
    "x_goat_storage_mb": 5120,
}
EXTRA_EDITOR = {
    "qty": 2.0,
    "x_goat_editors": 1,
    "x_goat_viewers": 0,
    "x_goat_projects": 0,
    "x_goat_storage_mb": 0,
}
EXTRA_STORAGE = {
    "qty": 10.0,
    "x_goat_editors": 0,
    "x_goat_viewers": 0,
    "x_goat_projects": 0,
    "x_goat_storage_mb": 1024,
}


def test_base_plus_addons():
    payload = compute_entitlement(order(), [BASE_LINE, EXTRA_EDITOR, EXTRA_STORAGE])
    assert payload["organization_id"] == "b65e040a-f8f0-453f-9888-baa2b9342cce"
    assert payload["total_editors"] == 5  # 3 base + 2x1
    assert payload["total_viewers"] == 2
    assert payload["total_projects"] == 50
    assert payload["total_storage"] == 15360  # 5120 + 10x1024
    assert payload["extras"] == []
    assert payload["suspended"] is False
    assert payload["on_trial"] is False  # a real subscription ends any trial
    assert payload["reset_usage"] is False
    assert payload["plan_renewal_date"] == "2026-08-01"


def test_order_level_override_wins():
    payload = compute_entitlement(order(x_goat_editors=25), [BASE_LINE, EXTRA_EDITOR])
    assert payload["total_editors"] == 25  # negotiated deal
    assert payload["total_viewers"] == 2  # others still computed


def test_white_label_checkbox_becomes_extra():
    payload = compute_entitlement(order(x_goat_white_label=True), [BASE_LINE])
    assert payload["extras"] == ["white_label"]


def test_churn_pushes_suspension():
    payload = compute_entitlement(order(subscription_state="6_churn"), [BASE_LINE])
    assert payload["suspended"] is True


def test_paused_pushes_suspension():
    payload = compute_entitlement(order(subscription_state="4_paused"), [BASE_LINE])
    assert payload["suspended"] is True


def test_quotation_states_not_pushed():
    for state in ("1_draft", "2_renewal", "5_renewed", "7_upsell"):
        assert compute_entitlement(order(subscription_state=state), [BASE_LINE]) is None


def test_unlinked_subscription_not_pushed():
    assert compute_entitlement(order(x_goat_organization_id=False), [BASE_LINE]) is None


def test_missing_renewal_date_omitted():
    payload = compute_entitlement(order(next_invoice_date=False), [BASE_LINE])
    assert "plan_renewal_date" not in payload


def test_missing_feature_field_means_not_granted():
    stripped = order()
    del stripped["x_goat_white_label"]  # checkbox not yet created in Odoo
    payload = compute_entitlement(stripped, [BASE_LINE])
    assert payload["extras"] == []


def test_monthly_credits_from_products_and_packs():
    base = {**BASE_LINE, "x_goat_credits": 25000}
    pack = {**EXTRA_EDITOR, "qty": 2.0, "x_goat_editors": 0, "x_goat_credits": 10000}
    payload = compute_entitlement(order(), [base, pack])
    assert payload["total_credits"] == 45000  # 25,000 + 2 x 10,000


def test_credits_override_on_the_subscription_wins():
    base = {**BASE_LINE, "x_goat_credits": 25000}
    payload = compute_entitlement(order(x_goat_credits=60000), [base])
    assert payload["total_credits"] == 60000


def test_no_credits_in_the_catalogue_leaves_the_allowance_alone():
    # An Odoo without the field (or products without credits) must not send 0,
    # which would block every tool run.
    payload = compute_entitlement(order(), [BASE_LINE])
    assert "total_credits" not in payload


class _FakeOdoo:
    """Just enough of Odoo's XML-RPC for the customer lookup."""

    def __init__(self, partners: dict[int, dict]) -> None:
        self.partners = partners

    def __call__(self, model, method, ids, fields=None):
        assert (model, method) == ("res.partner", "read")
        return [self.partners[i] for i in ids if i in self.partners]


def _task(partners: dict[int, dict], linked: bool = True):
    from goatlib.tasks.odoo_entitlement import OdooEntitlementTask

    task = object.__new__(OdooEntitlementTask)
    task._kw = _FakeOdoo(partners)
    task._partners_linked = linked
    return task


def test_a_subscription_without_organization_takes_its_customers():
    task = _task(
        {
            5: {"id": 5, "commercial_partner_id": [9, "Stadt Beispiel"]},
            9: {"id": 9, "x_goat_organization_id": "org-9"},
        }
    )
    assert task._organization_of_customer({"partner_id": [5, "Anna"]}) == "org-9"


def test_a_customer_without_organization_leaves_it_unlinked():
    task = _task(
        {
            5: {"id": 5, "commercial_partner_id": [5, "Firma"]},
        }
    )
    assert task._organization_of_customer({"partner_id": [5, "Firma"]}) is None
    assert (
        _task({}, linked=False)._organization_of_customer({"partner_id": [5, "x"]})
        is None
    )


# --- per-organization entitlement ---------------------------------------------

ORG = "b65e040a-f8f0-453f-9888-baa2b9342cce"


def sub(oid, state="3_progress", write_date="2026-10-01 10:00:00", **kw):
    return (
        order(
            id=oid,
            name=f"S{oid}",
            subscription_state=state,
            write_date=write_date,
            **kw,
        ),
        [BASE_LINE],
    )


def test_active_subscription_beats_a_newer_cancelled_one():
    from goatlib.tasks.odoo_entitlement import merge_entitlements

    payload = merge_entitlements(
        [
            sub(1, "3_progress", "2026-09-01 08:00:00"),
            sub(2, "6_churn", "2026-10-15 08:00:00"),  # edited later, still loses
        ]
    )
    assert payload["suspended"] is False
    assert payload["total_editors"] == 3  # only the active one counts
    # the push reflects both subscriptions: its time is the later change
    assert payload["as_of"] == "2026-10-15T08:00:00+00:00"


def test_active_subscriptions_add_up_with_per_order_overrides():
    from goatlib.tasks.odoo_entitlement import merge_entitlements

    a = sub(1, write_date="2026-09-01 08:00:00", x_goat_white_label=True)
    b = sub(
        2,
        write_date="2026-10-02 09:30:00",
        x_goat_editors=10,
        next_invoice_date="2026-07-01",
    )
    payload = merge_entitlements([a, b])
    assert payload["total_editors"] == 3 + 10  # override replaces order b's lines
    assert payload["total_viewers"] == 4
    assert payload["extras"] == ["white_label"]
    assert payload["plan_renewal_date"] == "2026-07-01"  # the earlier renewal
    assert payload["as_of"] == "2026-10-02T09:30:00+00:00"


def test_credits_only_when_an_active_subscription_grants_some():
    from goatlib.tasks.odoo_entitlement import merge_entitlements

    credit_line = {**BASE_LINE, "x_goat_credits": 1000}
    a = (order(subscription_state="3_progress"), [credit_line])
    b = (order(subscription_state="3_progress"), [credit_line])
    c = (order(subscription_state="3_progress"), [BASE_LINE])
    assert merge_entitlements([a, b, c])["total_credits"] == 2000
    assert "total_credits" not in merge_entitlements([c])


def test_without_an_active_subscription_the_latest_one_suspends():
    from goatlib.tasks.odoo_entitlement import merge_entitlements

    payload = merge_entitlements(
        [
            sub(1, "6_churn", "2026-05-01 08:00:00", x_goat_editors=9),
            sub(2, "4_paused", "2026-08-01 08:00:00", x_goat_editors=4),
        ]
    )
    assert payload["suspended"] is True
    assert payload["total_editors"] == 4  # from the most recent one
    assert payload["as_of"] == "2026-08-01T08:00:00+00:00"


def test_nothing_pushable_gives_no_payload():
    from goatlib.tasks.odoo_entitlement import merge_entitlements

    assert merge_entitlements([]) is None
    assert merge_entitlements([sub(1, "1_draft")]) is None


def test_as_of_is_iso_utc_and_absent_without_write_date():
    from goatlib.tasks.odoo_entitlement import to_iso_utc

    assert to_iso_utc("2026-10-20 12:34:56") == "2026-10-20T12:34:56+00:00"
    assert to_iso_utc(False) is None
    payload = compute_entitlement(order(), [BASE_LINE])
    assert "as_of" not in payload


class _Pusher:
    """A task with subscriptions held in memory instead of Odoo."""

    def __init__(self, subs_by_org, fail=(), gone=()):
        from goatlib.tasks.odoo_entitlement import OdooEntitlementTask

        self.task = object.__new__(OdooEntitlementTask)
        self.subs_by_org = subs_by_org
        self.by_id = {
            o["id"]: (o, lines) for subs in subs_by_org.values() for o, lines in subs
        }
        self.fail, self.gone = set(fail), set(gone)
        self.posted: list[dict] = []
        t = self.task
        t.core_url, t.webhook_secret = "http://core", "s"
        t._partners_linked = False
        t._kw = self._kw
        t._fetch = lambda oid: self.by_id[oid]
        t._organization_subscriptions = lambda org: self.subs_by_org[org]

    def _kw(self, model, method, *args, **kw):
        assert (model, method) == ("sale.order", "search")
        return list(self.by_id)

    def patch_httpx(self, monkeypatch):
        import httpx

        def post(url, headers, json, timeout):
            org = json["organization_id"]
            if org in self.fail:
                return httpx.Response(500, request=httpx.Request("POST", url))
            if org in self.gone:
                return httpx.Response(409, request=httpx.Request("POST", url))
            self.posted.append(json)
            return httpx.Response(200, request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx, "post", post)


def _orgs():
    def s(oid, org, state="3_progress"):
        o, lines = sub(oid, state, x_goat_organization_id=org)
        return o, lines

    return {
        "orgA": [s(1, "orgA", "6_churn"), s(2, "orgA")],
        "orgB": [s(3, "orgB")],
        "orgC": [s(4, "orgC")],
        "orgD": [s(5, "orgD")],
    }


def test_reconcile_pushes_each_organization_once(monkeypatch):
    p = _Pusher(_orgs())
    p.patch_httpx(monkeypatch)
    result = p.task.reconcile()
    assert sorted(x["organization_id"] for x in p.posted) == [
        "orgA",
        "orgB",
        "orgC",
        "orgD",
    ]
    assert result["pushed"] == 4
    assert result["status"] == "ok"
    assert result["errors"] == []
    org_a = next(x for x in p.posted if x["organization_id"] == "orgA")
    assert org_a["suspended"] is False  # the cancelled one did not overwrite


def test_reconcile_continues_after_a_failure_and_skips_deleted_orgs(monkeypatch):
    p = _Pusher(_orgs(), fail={"orgB"}, gone={"orgC"})
    p.patch_httpx(monkeypatch)
    result = p.task.reconcile()
    assert sorted(x["organization_id"] for x in p.posted) == ["orgA", "orgD"]
    assert result["status"] == "partial"
    assert [e["organization_id"] for e in result["errors"]] == ["orgB"]
    assert result["pushed"] == 2
    assert result["skipped"] == 1  # the 409


def test_reconcile_dry_run_posts_nothing(monkeypatch):
    p = _Pusher(_orgs())
    p.patch_httpx(monkeypatch)
    result = p.task.reconcile(dry_run=True)
    assert p.posted == []
    assert result["computed"] == 4


def test_push_order_pushes_the_whole_organization(monkeypatch):
    p = _Pusher(_orgs())
    p.patch_httpx(monkeypatch)
    # the live trigger is the OLD cancelled order of orgA
    result = p.task.push_order(1)
    assert result["status"] == "pushed"
    assert result["orders"] == ["S1", "S2"]
    assert p.posted[0]["suspended"] is False


def test_push_order_reports_a_deleted_organization_as_skipped(monkeypatch):
    p = _Pusher(_orgs(), gone={"orgB"})
    p.patch_httpx(monkeypatch)
    assert p.task.push_order(3)["status"] == "skipped"


def test_non_https_odoo_url_is_refused_except_localhost():
    import pytest
    from goatlib.tasks.odoo_entitlement import check_odoo_url

    assert check_odoo_url("https://odoo.example.com")
    assert check_odoo_url("http://localhost:8069")
    assert check_odoo_url("http://127.0.0.1:8069")
    with pytest.raises(RuntimeError):
        check_odoo_url("http://odoo.example.com")


def test_xmlrpc_transports_carry_a_timeout():
    from goatlib.tasks.odoo_entitlement import (
        XMLRPC_TIMEOUT_SECONDS,
        _proxy,
        _SafeTransport,
        _Transport,
    )

    for cls, url in (
        (_Transport, "http://localhost/x"),
        (_SafeTransport, "https://h/x"),
    ):
        t = cls()
        assert t.make_connection(url.split("/")[2]).timeout == XMLRPC_TIMEOUT_SECONDS
    assert _proxy("https://odoo.example.com/xmlrpc/2/common") is not None
