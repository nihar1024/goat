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
