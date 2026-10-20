# Odoo → GOAT entitlement contract

Direction (decided 2026-06-10, refined 2026-07-16): GOAT core is
billing-provider-agnostic. Odoo owns the customer/subscription/invoice/trial/
dunning lifecycle and pushes **entitlement state** into core through one
service-protected endpoint. Core stores and enforces that state; it never
talks to Odoo.

## Commercial model (decided 2026-07-16, prices and quotas 2026-10-17)

One base product plus per-unit add-ons — no tiers:

| Odoo product | Meaning | `x_goat_*` values |
|---|---|---|
| GOAT (id 8) | base subscription, the "Team" plan: 10,000 EUR/year incl. software training (2026-10-17) | editors 5, viewers 50, storage_mb 10240, projects 250, credits 75,000/month |
| GOAT Extra Editor User (id 9) | +1 editor per qty (1,500 EUR/year, 2026-10-17) | editors 1, credits 15,000/month |
| GOAT Extra Credits | +10,000 credits/month per qty (internal, for the rare heavy user; not on the website) | credits 10,000 |
| GOAT Extra Viewer User (id 13) | +1 viewer per qty | viewers 1 |
| GOAT Extra Project (id 14) | +1 project per qty | projects 1 |
| GOAT Extra Storage (GB) (id 15) | +1 GB per qty | storage_mb 1024 |

GOAT Professional (11) / Enterprise (12) are archived. All Odoo-side setup
(catalog, white-label checkbox, legacy plan-field removal, automation) lives
in one replayable CLI: `scripts/odoo/odoo_setup.py` (subcommands + `all`;
dry-run default, `--apply` to write, staging-guarded).

**Entitlement math** (computed by the Odoo automation when it builds the
payload):

```
total_<quota> = base.x_goat_<quota> + Σ(line qty × addon.x_goat_<quota>)
```

The `x_goat_*` fields on the subscription (`sale.order`) itself act as a
manual **override** for negotiated deals: when set (> 0), they win over the
computed value.

**Premium features** are NOT products. They are checkboxes on the
subscription's GOAT tab (e.g. `x_goat_white_label`), controlled by sales per
customer, and shipped in the payload as the `extras` list. Pricing for them
lives in the negotiated subscription price, invisibly to the catalog.

## Endpoint

```
POST /api/v2/webhooks/odoo/entitlement
X-Webhook-Secret: <ODOO_WEBHOOK_SECRET>
```

Auth: shared secret header, compared against core's `ODOO_WEBHOOK_SECRET`
setting. Unset secret ⇒ endpoint always answers 401 (the self-hosted /
no-billing state).

## Payload

```json
{
  "organization_id": "b65e040a-f8f0-453f-9888-baa2b9342cce",
  "total_editors": 5,
  "total_viewers": 2,
  "total_projects": 60,
  "total_storage": 15360,
  "total_credits": null,
  "extras": ["white_label"],
  "plan_renewal_date": "2026-08-01T00:00:00",
  "reset_usage": true
}
```

Semantics (all keys except `organization_id` optional — absent keys leave the
org row untouched):

| Key | Type | Meaning |
|---|---|---|
| `organization_id` | UUID | GOAT org id, from `sale.order.x_goat_organization_id`. The join key between the two systems — must be filled when a customer is wired up. |
| `total_editors` / `total_viewers` / `total_projects` | int \| null | capacity caps; `null` = unlimited |
| `total_storage` | float (MB) \| null | storage cap in MB; `null` = unlimited |
| `total_credits` | number \| null | consumption allowance (phase 2 — metering); `null` = unlimited |
| `extras` | list[str] \| null | granted premium features (grant-list). `null` = ALL enabled (self-hosted default), `[]` = none, else exactly the granted ones. Known values: `white_label`. |
| `plan_renewal_date` | ISO datetime | next renewal, informational + shown in UI |
| `suspended` | bool | suspend (churn) / reactivate the organization |
| `on_trial` | bool | the adapter always sends `false`: a real subscription ends any trial (conversion) |
| `reset_usage` | bool (default **false**) | zero `used_credits` (renewal semantics). Send `true` on a renewal. |
| `as_of` | ISO 8601 datetime (UTC) | the newest Odoo `write_date` among the subscriptions the payload was computed from. Core ignores a push whose `as_of` is older than the one it already applied (HTTP 200 `{"status": "stale"}`, nothing changes), so a delayed or replayed push cannot undo a newer one. Absent when Odoo gave no `write_date`: the push is applied. Stored in `organization.entitlement_as_of`. |

**Validation.** The payload is a typed model; unknown keys and wrong types
are refused with HTTP 422 and change nothing. `organization_id` must be a
UUID. `suspended`, `on_trial` and `reset_usage` must be JSON booleans (the
string `"false"` is refused, never read as true). Caps are non-negative
numbers (`null` = unlimited; the count caps must be whole numbers). `extras`
is a list of strings. `plan_renewal_date` and `as_of` are ISO 8601 with or
without offset; an offset is converted to UTC and stored as naive UTC.

**Responses.** `200 {"status": "ok"}` applied, `200 {"status": "stale"}`
ignored (older `as_of`), `404` unknown organization, `409` the organization
was deleted in GOAT (`DELETE /organizations/{id}` sets `deleted_at`): a push
never revives it, and the adapter reports it as skipped.

**One payload per organization.** An organization can have several
subscriptions (e.g. an old cancelled one next to the active one), so the
adapter never pushes subscriptions individually. It collects every
subscription of the organization in a pushable state (organization =
`sale.order.x_goat_organization_id`, else the customer company's) and sends one
payload:

- at least one active (`3_progress`) subscription: only the active ones count.
  Their per-line quotas add up (subscription-level overrides apply per order),
  `extras` is the union, `plan_renewal_date` the earliest renewal,
  `suspended: false`;
- none active: the most recently changed paused/churned subscription
  suspends the organization (`suspended: true`, zero quotas as before).

Not in the payload (deliberately): `plan_name` — plan names (and Stripe) are
REMOVED on this branch: no `PlanTypeEnum`, no `plan_name`/`stripe_id`
columns, no `/billing/plans`, no tier cards. **Merging this branch is
therefore gated on the Odoo cutover** (prod orgs backfilled into Odoo, the
automation live). Dunning mechanics stay Odoo-native — core only ever sees
the resulting caps/suspension.

Suspension (churn): same endpoint — `{"organization_id": ..., "suspended":
true, "reset_usage": false}` maps onto the existing `organization.suspended`
column (and `false` reactivates). Implemented in `apply_entitlement()`.

## Adapter (decided 2026-07-16: Windmill, not an Odoo addon)

Odoo stays configuration-only; all logic lives in this repo:

```
Odoo automation rule (on_create_or_write on sale.order, is_subscription,
watching subscription_state / order_line / x_goat_*)
  → native "Send Webhook Notification" action
      POSTs {_action, _id, _model, x_goat_organization_id}
  → Windmill f/goat/tasks/odoo_entitlement_push
      (goatlib/tasks/odoo_entitlement.py: reads the subscription over
       XML-RPC, computes the payload, POSTs to core with the secret)
  → core /webhooks/odoo/entitlement → apply_entitlement()
```

- Task modes: `order_id > 0` = push the whole organization of that order
  (webhook path); `order_id = 0` = reconcile every organization with a
  pushable subscription, each once (nightly 02:00 schedule — heals missed
  webhooks, and running it manually is the initial backfill). Reconcile
  handles each organization on its own: a failure is collected in the result
  (`errors`, status `partial`) and never stops the others; a `409` from core
  (organization deleted) is reported as skipped.
- Transport: XML-RPC calls time out after 30 s; `ODOO_URL` must be `https`
  (plain `http` only for `localhost` / `127.0.0.1`).
- Pushable states: `3_progress` (active), `4_paused` / `6_churn` (both push
  `suspended: true`). Quotation states (draft/renewal/renewed/upsell) are
  skipped — the confirmed subscription pushes.
- `reset_usage` is always `false` until credit metering (phase 2) exists;
  there is nothing to reset yet.
- Windmill env: `ODOO_URL`, `ODOO_DB`, `ODOO_BILLING_USER`, `ODOO_BILLING_API_KEY`, `CORE_URL`,
  `ODOO_WEBHOOK_SECRET`.
- Odoo side is created by `scripts/odoo/odoo_setup.py automation
  --webhook-url <windmill url>` (replayable; rerun after staging rebuilds).

**Wiring caveat (verify at first sync):** Odoo's webhook payload keys are
fixed (`_id`, `_model`, …) and the generated Windmill script expects
`order_id`. If Windmill rejects the unknown args, add a preprocessor to the
Windmill script (or a thin wrapper script) mapping `_id` → `order_id`.

## Lifecycle events → payloads

| Odoo event | Payload |
|---|---|
| subscription confirmed / changed / renewed | full quotas + extras, `suspended: false` |
| subscription paused / churned (no active one left) | full quotas + extras, `suspended: true` |
| subscription paused / churned while another is active | the active ones only, `suspended: false` |
| nightly reconcile | same as above, once per organization |

## Enforcement in core

- Capacity caps: org row `total_*` columns, enforced by
  `customer.check_organization()` (SQL authz) and `CRUDOrganization`
  helpers. `NULL` total = unlimited (SQL NULL comparison already skips the
  quota check).
- Premium features: `organization.extras` (nullable text[]). Resources that
  require a feature declare it in `resource.extras`; the SQL gate passes when
  `org.extras IS NULL` or the required extras are contained in the granted
  ones. Currently gated: `white_label` (public-project custom domain
  POST/DELETE + per-project tracking opt-in).
- `apply_entitlement()` in `crud_organization.py` is the single writer for
  entitlement state.

## Trials (GOAT-managed — decided 2026-07-17)

A trial is a product/CRM concern: there is no deal yet, so there is no Odoo
record. Odoo never learns about trials; it only ends them by pushing the
first real entitlement.

- **Start:** SaaS signup (`ODOO_WEBHOOK_SECRET` set) creates the org with
  `on_trial=true`, `plan_renewal_date = now + TRIAL_DAYS` (config, default
  30) and the `TRIAL_QUOTA_*` config quotas (default: 5 editors / 2 viewers / 5 GB / 50 projects /
  10,000 credits for the whole trial), `extras = []`.
- **Enforcement:** the `trial_expiry` Windmill task (daily 03:00) classifies
  trials and calls `POST /api/v2/webhooks/trial` (same secret):
  `stage=expiring` (default 3 days before the end — warning email to the
  org contact) and `stage=expired` (suspend + email). The warning window is
  exactly one day wide, so a daily run fires it once. The org stays
  `on_trial` when suspended — expiry is not conversion. Both stages are
  idempotent: `expired` acts only on an organization that is on trial, not
  suspended, not deleted and past `plan_renewal_date`, `expiring` only on one
  that is on trial and not suspended or deleted; otherwise core answers
  `200 {"status": "noop"}` without mail or report to Odoo.
- **Access:** an ended trial is also refused on access, without waiting for
  the daily task: `customer.check_organization()` rejects an organization that
  is `on_trial` with `plan_renewal_date` in the past like a suspended one.
- **Conversion:** sales links + confirms the Odoo subscription; the
  entitlement push carries `on_trial: false` and `suspended: false`, which
  both ends the trial and reactivates an expired-suspended org.
- **Extension:** superuser bumps `plan_renewal_date` (manual admin action).
- The web UI (trial chip, days-left) reads only `on_trial` +
  `plan_renewal_date` — no changes needed.

## Reports to Odoo and their retry

core reports trials, joins and status to Odoo in the background
(`core.accounts`, only with `ODOO_BILLING_API_KEY`). A report that fails sets
`organization.odoo_sync_pending`; a loop in every core replica
(`ODOO_SYNC_RETRY_SECONDS`, default 600) re-sends the trial (when Odoo has no
company yet), the status and the joins of members without `odoo_contact_id`
for the flagged organizations, then clears the flag. Odoo's operations are
idempotent, so replicas doing it at once is harmless.

## Self-hosted

No Odoo, no adapter, nothing to configure: `ODOO_WEBHOOK_SECRET` unset keeps
the endpoint inert; orgs get env-driven defaults (`DEFAULT_PLAN_NAME`,
`DEFAULT_QUOTA_*`); `extras = NULL` ⇒ every premium feature enabled.

## Pending DB changes (hand-written migration, NOT yet created or applied)

- `organization.total_*` → nullable; `total_credits`/`used_credits` → Numeric
- `organization.extras` → new nullable text[] column
- `organization.plan_name` / `stripe_id` → dropped (plans + Stripe removed)
- `organization` CRM firmographics (`industry`, `department`, `use_case`,
  `location`, `phone_number`, `size`) → dropped — the canonical copy lives in
  the CRM (HubSpot today, Odoo CRM after the migration)
- `resource.plan_names` → renamed `extras` (text[]), re-seeded values
- re-install `customer.check_organization()` from the updated SQL source

All steps are existence-guarded: the `init` baseline builds fresh DBs from
current models (already the end state), so the migration no-ops there.

The migration is `0012_billing_and_usage` (after `0011_layer_serial_counter`), together with usage metering.

`0013_billing_hardening` adds `organization.entitlement_as_of`,
`organization.deleted_at`, `organization.odoo_sync_pending` (with a partial
index) and the unique partial index `uq_credit_usage_compute_job` on
`credit_usage ((payload->>'job_id')) WHERE category = 'compute'`, which makes a
compute charge idempotent per job. It refuses to run, naming the count, if the
ledger already holds a job charged twice: resolve those rows first.

## Odoo instances

- Production: never test against it.
- Staging (an Odoo.sh copy of production): its URL and database name change
  on every rebuild, so set `ODOO_URL` / `ODOO_DB` again after each one.
  Staging config is wiped on rebuild: keep every Odoo-side change scripted and
  replayable (`scripts/odoo/odoo_setup.py`).
