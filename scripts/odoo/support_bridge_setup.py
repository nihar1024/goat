"""Set up the least-privilege "GOAT Support Bridge" in an Odoo database.

    export ODOO_URL=https://odoo-staging.example.org
    export ODOO_DB=odoo-staging
    export ODOO_ADMIN_KEY=...      # an admin's API key for that database
    export GOAT_URL=https://goat.example.org   # the GOAT the emails link to
    python scripts/odoo/support_bridge_setup.py plan              # dry run
    python scripts/odoo/support_bridge_setup.py plan --apply      # write
    python scripts/odoo/support_bridge_setup.py create-key --apply  # prints the bridge key once
    python scripts/odoo/support_bridge_setup.py rotate-key --apply  # new key; revoke the old one after deploy

Staging only unless --production is passed. Idempotent: records are found
by name; the server action code, the template patch and the inherited
notification-layout views are re-applied.
Verified design: support tickets spec §6 (staging spike 2026-09-30).
"""

import argparse
import http.cookiejar
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from support_bridge_action import action_code  # noqa: E402

GROUP_NAME = "GOAT Support Bridge"
LOGIN = "goat-support-bridge@plan4better.de"
TEAM_NAME = "Customer Care"
ACTION_NAME = "GOAT: post message as ticket participant"
KEY_DAYS = 180
PORTAL_GROUP_XMLID = "base.group_portal"

# model -> (read, write, create, unlink); verified on staging 2026-09-30.
ACCESS: dict[str, tuple[bool, bool, bool, bool]] = {
    "helpdesk.ticket": (True, True, True, False),
    "helpdesk.team": (True, False, False, False),
    "helpdesk.stage": (True, False, False, False),
    "helpdesk.tag": (True, False, False, False),
    "helpdesk.sla": (True, False, False, False),
    "helpdesk.sla.status": (True, False, False, False),
    # read only: new contacts come from the server action (op "contact"), so a
    # leaked key cannot edit existing partners
    "res.partner": (True, False, False, False),
    "res.partner.category": (True, False, False, False),
    "mail.message": (True, False, False, False),
    "mail.message.subtype": (True, False, False, False),
    "mail.tracking.value": (True, False, False, False),
    "mail.followers": (True, False, False, False),
    "mail.compose.message": (False, False, True, False),
    "mail.template": (True, False, False, False),
    "ir.attachment": (True, False, True, False),
    "rating.rating": (True, False, False, False),
    "ir.actions.server": (True, False, False, False),
}
# (name, model, domain, read, write, create, unlink); "{team_id}" / "{action_id}" filled in.
RULES: list[tuple[str, str, str, bool, bool, bool, bool]] = [
    (
        "goat bridge: Customer Care tickets only",
        "helpdesk.ticket",
        "[('team_id', '=', {team_id})]",
        True,
        True,
        True,
        False,
    ),
    (
        "goat bridge: read all contacts (match by email)",
        "res.partner",
        "[(1, '=', 1)]",
        True,
        False,
        False,
        False,
    ),
    (
        "goat bridge: ticket messages only",
        "mail.message",
        "[('model', '=', 'helpdesk.ticket')]",
        True,
        False,
        False,
        False,
    ),
    (
        "goat bridge: ticket followers only",
        "mail.followers",
        "[('res_model', '=', 'helpdesk.ticket')]",
        True,
        False,
        False,
        False,
    ),
    (
        "goat bridge: ticket attachments only",
        "ir.attachment",
        "[('res_model', 'in', ['helpdesk.ticket', 'mail.message'])]",
        True,
        False,
        True,
        False,
    ),
    (
        "goat bridge: ticket ratings only",
        "rating.rating",
        "[('res_model', '=', 'helpdesk.ticket')]",
        True,
        False,
        False,
        False,
    ),
    (
        "goat bridge: helpdesk email templates only",
        "mail.template",
        "[('model', '=', 'helpdesk.ticket')]",
        True,
        False,
        False,
        False,
    ),
    (
        "goat bridge: only its own server action",
        "ir.actions.server",
        "[('id', '=', {action_id})]",
        True,
        False,
        False,
        False,
    ),
]
# Rights and rules of earlier versions of this script that must not survive a re-run.
LEGACY_ACCESS = ["mail.mail"]  # (model)
LEGACY_RULES = [  # (rule name, model)
    ("goat bridge: create/edit individuals only", "res.partner"),
    ("goat bridge: own mails only", "mail.mail"),
    # contacts are created by the server action since 2026-10-01
    ("goat bridge: create individuals only", "res.partner"),
    ("goat bridge: edit customer contacts only", "res.partner"),
]
FIELDS = [
    ("x_goat_organization_id", "GOAT Organization ID"),
    ("x_goat_user_id", "GOAT User ID"),
    ("x_goat_request_id", "GOAT Request ID"),
]
TEMPLATES = ["Helpdesk: Ticket Received", "Helpdesk: Ticket Closed"]
_PORTAL_HREF = 't-att-href="object.get_portal_url()"'


@dataclass
class Step:
    kind: str
    description: str
    detail: dict[str, Any] = field(default_factory=dict)


class Odoo:
    """Minimal JSON-2 client with an admin key (setup only; core has its own)."""

    def __init__(self, url: str, db: str, key: str) -> None:
        self.url, self.db, self.key = url.rstrip("/"), db, key

    def call(self, model: str, method: str, **kw: Any) -> Any:
        # Names of groups, actions, templates, teams... are translated: always look
        # them up (and write them) in the source language unless a call says otherwise.
        kw["context"] = {"lang": "en_US", **(kw.get("context") or {})}
        req = urllib.request.Request(
            f"{self.url}/json/2/{model}/{method}",
            data=json.dumps(kw).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"bearer {self.key}",
                "X-Odoo-Database": self.db,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            raise SystemExit(
                f"HTTP {e.code} on {model}.{method}: {e.read().decode()[:600]}"
            ) from None


def guard_target(url: str, db: str, *, production: bool) -> None:
    if "staging" not in url or "staging" not in db:
        if not production:
            raise SystemExit(f"refusing to touch {url} ({db}) without --production")


_GOAT_URL = re.compile(
    r"(https://[A-Za-z0-9.-]+|http://(localhost|127\.0\.0\.1))(:[0-9]{1,5})?"
    r"(/[A-Za-z0-9._~/-]*)?"
)


def validate_goat_url(goat_url: str) -> str:
    """The URL is written into email templates as Python source: keep it boring."""
    if not _GOAT_URL.fullmatch(goat_url):
        raise SystemExit(
            f"GOAT_URL {goat_url!r} must be an https:// URL (http:// only for localhost) "
            "without quotes, whitespace or angle brackets"
        )
    return goat_url


# A ticket belongs to GOAT when core created it (x_goat_user_id is always set, also for
# users without an organization) or stamped it with an organization (tickets that
# started as emails from a member). The web page is /support/<ref>, no org needed.
_IS_GOAT = "(object.x_goat_user_id or object.x_goat_organization_id)"
_OLD_IS_GOAT = "object.x_goat_organization_id"  # round-2 form, migrated on re-run


def _goat_href(goat_url: str) -> str:
    return (
        f"t-att-href=\"('{goat_url.rstrip('/')}/support/%s' % object.ticket_ref) "
        f'if {_IS_GOAT} else object.get_portal_url()"'
    )


_PATCHED_HREF = re.compile(
    r"""t-att-href="\('[^']*/support/%s' % object\.ticket_ref\) """
    r"""if (?:\(object\.x_goat_user_id or object\.x_goat_organization_id\)"""
    r"""|object\.x_goat_organization_id) else object\.get_portal_url\(\)\""""
)


def patch_template_body(body: str, goat_url: str) -> str:
    """For GOAT tickets the "view ticket" button opens GOAT instead of the Odoo portal.

    Idempotent, re-points an already patched button when GOAT_URL changed and
    migrates the earlier form (organization id only) to the current condition.
    Raises ValueError when there is nothing it recognises to patch, so a
    template that Odoo changed under us fails loudly instead of silently
    keeping the portal link.
    """
    href = _goat_href(goat_url)
    if _PATCHED_HREF.search(body):
        return _PATCHED_HREF.sub(lambda _m: href, body)
    if "x_goat_" in body:
        raise ValueError("contains x_goat_ fields but not as the expected button link")
    if _PORTAL_HREF not in body:
        raise ValueError(
            "the portal button (object.get_portal_url()) was not found; nothing to patch"
        )
    return body.replace(_PORTAL_HREF, href)


_CLOSE_LINK = "/my/ticket/close"
_CLOSE_COND = 't-if="object.team_id.allow_portal_ticket_closing"'
_CLOSE_COND_GOAT = (
    f't-if="object.team_id.allow_portal_ticket_closing and not {_IS_GOAT}"'
)
_CLOSE_COND_OLD = (
    't-if="object.team_id.allow_portal_ticket_closing ' f'and not {_OLD_IS_GOAT}"'
)


def hide_close_button_for_goat_tickets(body: str) -> str:
    """The "Close Ticket" button opens the Odoo portal: hide it for GOAT tickets.

    Idempotent and migrates the earlier condition. Bodies without that button
    (other templates) are returned as they are; a button we cannot find the
    wrapping condition of raises.
    """
    if _CLOSE_LINK not in body or _CLOSE_COND_GOAT in body:
        return body
    for known in (_CLOSE_COND_OLD, _CLOSE_COND):
        if known in body:
            return body.replace(known, _CLOSE_COND_GOAT)
    raise ValueError(
        "the close-ticket button is not wrapped in the expected t-if; nothing to patch"
    )


# Reply notifications (an agent answers in Odoo) are not mail templates: Odoo wraps the
# message in a QWeb notification layout whose button and header link use
# button_access['url'] (the portal /mail/view link for customers). An inherited view on
# each layout re-points that url for GOAT tickets, for recipient groups without an
# internal user (agents keep the Odoo link). Groups Odoo shows no button (followers
# without a user, e.g. GOAT colleagues on the ticket) get the GOAT button too, with the
# title Odoo already computed for every group ("View Ticket", translated). A render
# without recipient data (not a per-group notification) keeps Odoo's link. Extensions
# of the base layouts also reach their primary children (responsible signature, ...).
LAYOUT_VIEWS = {  # layout xmlid -> name of our inherited view
    "mail.mail_notification_layout": "GOAT: support reply links to GOAT",
    "mail.mail_notification_light": "GOAT: support reply links to GOAT (light layout)",
}
_IS_GOAT_RECORD = "(record.x_goat_user_id or record.x_goat_organization_id)"
# These views extend Odoo's global mail layouts: if an xpath stops matching (after an
# Odoo upgrade), combining them fails and every notification email of the database
# fails with it. So the anchor is structural, not a statement Odoo might rename: the
# first element inside the template root, which exists in any layout and comes before
# everything the layout computes (show_header from has_button_access in particular).
_LAYOUT_ANCHOR = "/*/*[1]"
# What the override relies on: the layout shows its button from these two values. If an
# upgrade drops them, the view would do nothing; `plan` deactivates it and says so.
_LAYOUT_NEEDS = ("has_button_access", "button_access['url']")


def layout_view_arch(goat_url: str) -> str:
    """The inherited view arch: sets the GOAT button before the layout reads it."""
    cond = (
        "record and record._name == 'helpdesk.ticket' "
        f"and {_IS_GOAT_RECORD} "
        "and recipients_data is not None "
        "and not [r for r in recipients_data if r.get('type') == 'user']"
    )
    url = f"'{goat_url.rstrip('/')}/support/%s' % record.ticket_ref"
    title = "(button_access or {}).get('title') or model_description or record_name"
    return (
        "<data>\n"
        f'    <xpath expr="{_LAYOUT_ANCHOR}" position="before">\n'
        f'        <t t-if="{cond}">\n'
        '            <t t-set="button_access" '
        f't-value="dict(button_access or {{}}, url={url}, title={title})"/>\n'
        '            <t t-set="has_button_access" t-value="True"/>\n'
        "        </t>\n"
        "    </xpath>\n"
        "</data>"
    )


def _first(client: Any, model: str, domain: list) -> int | None:
    ids = client.call(model, "search", domain=domain, limit=1)
    return ids[0] if ids else None


def plan(client: Any, *, team_id: int, goat_url: str) -> list[Step]:
    validate_goat_url(goat_url)
    team = client.call(
        "helpdesk.team",
        "search_read",
        domain=[["id", "=", team_id]],
        fields=["name"],
        limit=1,
    )
    if not team:
        raise SystemExit(f"helpdesk team {team_id} does not exist")
    if team[0]["name"] != TEAM_NAME:
        raise SystemExit(
            f"helpdesk team {team_id} is {team[0]['name']!r}, expected {TEAM_NAME!r}; "
            "refusing to scope the bridge to it (check --team-id)"
        )
    steps: list[Step] = [
        Step("team", f"team {team_id} is {TEAM_NAME!r}: the bridge is scoped to it")
    ]
    for name, label in FIELDS:
        if not _first(
            client,
            "ir.model.fields",
            [["model", "=", "helpdesk.ticket"], ["name", "=", name]],
        ):
            steps.append(
                Step(
                    "field",
                    f"create helpdesk.ticket.{name}",
                    {"name": name, "label": label},
                )
            )
    group_exists = bool(_first(client, "res.groups", [["name", "=", GROUP_NAME]]))
    steps.append(
        Step(
            "group",
            f'{"update" if group_exists else "create"} group "{GROUP_NAME}" '
            f"(api_key_duration {KEY_DAYS})",
        )
    )
    for model, (r, w, c, u) in ACCESS.items():
        steps.append(
            Step(
                "access",
                f"access {model}: r={r} w={w} c={c} d={u}",
                {
                    "model": model,
                    "perm_read": r,
                    "perm_write": w,
                    "perm_create": c,
                    "perm_unlink": u,
                },
            )
        )
    steps.append(
        Step(
            "server_action",
            f'create/update server action "{ACTION_NAME}"',
            {"team_id": team_id},
        )
    )
    action_id = _first(client, "ir.actions.server", [["name", "=", ACTION_NAME]])
    for rule in RULES:
        shown = rule[2].format(
            team_id=team_id, action_id=action_id or "<id of the new server action>"
        )
        steps.append(
            Step(
                "rule",
                f'rule "{rule[0]}" on {rule[1]}: {shown}',
                {"rule": rule, "team_id": team_id},
            )
        )
    for name in TEMPLATES:
        steps.append(
            Step(
                "template_patch",
                f'patch "{name}" button to open GOAT for GOAT tickets',
                {"name": name, "goat_url": goat_url},
            )
        )
    arch = layout_view_arch(goat_url)
    for layout, view_name in LAYOUT_VIEWS.items():
        parent_id = _layout_id(client, layout)
        existing = _layout_view(client, view_name, parent_id)
        missing = layout_assumptions_missing(_layout_arch(client, parent_id))
        if missing:
            action = "deactivate" if existing and existing["active"] else "skip"
            what = (
                f"deactivate view {view_name!r}" if action == "deactivate" else "skip"
            )
            steps.append(
                Step(
                    "layout_view",
                    f"WARNING {layout} no longer uses {', '.join(missing)}: {what}; "
                    "reply emails keep Odoo's portal link until this script is updated",
                    {
                        "action": action,
                        "layout": layout,
                        "parent_id": parent_id,
                        "view_id": existing["id"] if existing else None,
                        "name": view_name,
                        "arch": arch,
                    },
                )
            )
            continue
        if not existing:
            action = "create"
        elif existing["arch_db"].strip() == arch and existing["active"]:
            action = "keep"
        else:
            action = "update"
        shown = "up to date:" if action == "keep" else action
        steps.append(
            Step(
                "layout_view",
                f'{shown} view "{view_name}" (inherits {layout}): '
                "reply buttons open GOAT for GOAT tickets",
                {
                    "action": action,
                    "layout": layout,
                    "parent_id": parent_id,
                    "view_id": existing["id"] if existing else None,
                    "name": view_name,
                    "arch": arch,
                },
            )
        )
    for model in LEGACY_ACCESS:
        if _first(client, "ir.model.access", [["name", "=", f"goat bridge: {model}"]]):
            steps.append(
                Step("remove_access", f"remove access on {model}", {"model": model})
            )
    for name, model in LEGACY_RULES:
        if _first(client, "ir.rule", [["name", "=", name]]):
            steps.append(
                Step(
                    "remove_rule",
                    f'remove rule "{name}" on {model}',
                    {"name": name, "model": model},
                )
            )
    user_exists = bool(
        _first(
            client,
            "res.users",
            [["login", "=", LOGIN], ["active", "in", [True, False]]],
        )
    )
    steps.append(
        Step(
            "user",
            f"{'update' if user_exists else 'create'} portal user {LOGIN} "
            f"with groups [Portal, {GROUP_NAME}]",
        )
    )
    return steps


def apply(client: Any, steps: list[Step], *, team_id: int) -> None:
    ticket_model = _first(client, "ir.model", [["model", "=", "helpdesk.ticket"]])
    portal = client.call(
        "ir.model.data",
        "search_read",
        domain=[["module", "=", "base"], ["name", "=", "group_portal"]],
        fields=["res_id"],
        limit=1,
    )
    portal_gid = portal[0]["res_id"]
    group_id = _first(client, "res.groups", [["name", "=", GROUP_NAME]])
    action_id = _first(client, "ir.actions.server", [["name", "=", ACTION_NAME]])
    for step in steps:
        print("APPLY ", step.description)
        if step.kind == "field":
            client.call(
                "ir.model.fields",
                "create",
                vals_list=[
                    {
                        "model_id": ticket_model,
                        "name": step.detail["name"],
                        "field_description": step.detail["label"],
                        "ttype": "char",
                        "state": "manual",
                        "index": True,
                    }
                ],
            )
        elif step.kind == "group":
            vals = {
                "name": GROUP_NAME,
                "api_key_duration": KEY_DAYS,
                "comment": "Service user for the in-app GOAT support page. Customer Care tickets only; no delete.",
            }
            if group_id:
                client.call("res.groups", "write", ids=[group_id], vals=vals)
            else:
                group_id = client.call("res.groups", "create", vals_list=[vals])[0]
        elif step.kind == "access":
            name = f"goat bridge: {step.detail['model']}"
            model_id = _first(
                client, "ir.model", [["model", "=", step.detail["model"]]]
            )
            vals = {
                k: step.detail[k]
                for k in ("perm_read", "perm_write", "perm_create", "perm_unlink")
            }
            existing = _first(
                client,
                "ir.model.access",
                [["name", "=", name], ["group_id", "=", group_id]],
            )
            if existing:
                client.call(
                    "ir.model.access",
                    "write",
                    ids=[existing],
                    vals={"model_id": model_id, **vals},
                )
            else:
                client.call(
                    "ir.model.access",
                    "create",
                    vals_list=[
                        {
                            "name": name,
                            "model_id": model_id,
                            "group_id": group_id,
                            **vals,
                        }
                    ],
                )
        elif step.kind == "server_action":
            vals = {
                "name": ACTION_NAME,
                "model_id": ticket_model,
                "state": "code",
                "code": action_code(group_id, team_id),
                "group_ids": [[6, 0, [group_id]]],
            }
            if action_id:
                client.call("ir.actions.server", "write", ids=[action_id], vals=vals)
            else:
                action_id = client.call(
                    "ir.actions.server", "create", vals_list=[vals]
                )[0]
        elif step.kind == "rule":
            name, model, domain, r, w, c, u = step.detail["rule"]
            model_id = _first(client, "ir.model", [["model", "=", model]])
            vals = {
                "model_id": model_id,
                "domain_force": domain.format(team_id=team_id, action_id=action_id),
                "groups": [[6, 0, [group_id]]],
                "perm_read": r,
                "perm_write": w,
                "perm_create": c,
                "perm_unlink": u,
            }
            existing = _first(
                client, "ir.rule", [["name", "=", name], ["model_id", "=", model_id]]
            )
            if existing:
                client.call("ir.rule", "write", ids=[existing], vals=vals)
            else:
                client.call("ir.rule", "create", vals_list=[{"name": name, **vals}])
        elif step.kind == "remove_access":
            ids = client.call(
                "ir.model.access",
                "search",
                domain=[
                    ["name", "=", f"goat bridge: {step.detail['model']}"],
                    ["group_id", "=", group_id],
                ],
            )
            if ids:
                client.call("ir.model.access", "unlink", ids=ids)
        elif step.kind == "remove_rule":
            model_id = _first(
                client, "ir.model", [["model", "=", step.detail["model"]]]
            )
            ids = client.call(
                "ir.rule",
                "search",
                domain=[
                    ["name", "=", step.detail["name"]],
                    ["model_id", "=", model_id],
                ],
            )
            if ids:
                client.call("ir.rule", "unlink", ids=ids)
        elif step.kind == "template_patch":
            _patch_template(client, step.detail["name"], step.detail["goat_url"])
        elif step.kind == "layout_view":
            _apply_layout_view(client, step.detail)
        elif step.kind == "user":
            vals = {
                "name": "GOAT Support Bridge",
                "login": LOGIN,
                "group_ids": [[6, 0, [portal_gid, group_id]]],
            }
            uid = _first(
                client,
                "res.users",
                [["login", "=", LOGIN], ["active", "in", [True, False]]],
            )
            if uid:
                client.call("res.users", "write", ids=[uid], vals=vals)
            else:
                client.call(
                    "res.users",
                    "create",
                    vals_list=[vals],
                    context={"no_reset_password": True},
                )


def _patch_template(client: Any, name: str, goat_url: str) -> None:
    """Patch the body in every active language: body_html is a translated field."""
    # The template name is translated too, so look it up in the source language.
    tpl_id = _first(client, "mail.template", [["name", "=", name]])
    if not tpl_id:
        raise SystemExit(f"mail template {name!r} not found (looked up in en_US)")
    langs = [
        row["code"]
        for row in client.call(
            "res.lang", "search_read", domain=[["active", "=", True]], fields=["code"]
        )
    ]
    for lang in langs:
        (tpl,) = client.call(
            "mail.template",
            "read",
            ids=[tpl_id],
            fields=["body_html"],
            context={"lang": lang},
        )
        try:
            patched = hide_close_button_for_goat_tickets(
                patch_template_body(tpl["body_html"], goat_url)
            )
        except ValueError as e:
            raise SystemExit(f"mail template {name!r} [{lang}]: {e}") from None
        if patched != tpl["body_html"]:
            client.call(
                "mail.template",
                "write",
                ids=[tpl_id],
                vals={"body_html": patched},
                context={"lang": lang},
            )


def _layout_id(client: Any, xmlid: str) -> int:
    module, name = xmlid.split(".")
    rows = client.call(
        "ir.model.data",
        "search_read",
        domain=[
            ["module", "=", module],
            ["name", "=", name],
            ["model", "=", "ir.ui.view"],
        ],
        fields=["res_id"],
        limit=1,
    )
    if not rows:
        raise SystemExit(f"notification layout {xmlid} not found")
    return rows[0]["res_id"]


def _layout_arch(client: Any, view_id: int) -> str:
    rows = client.call("ir.ui.view", "read", ids=[view_id], fields=["arch_db"])
    return (rows[0].get("arch_db") or "") if rows else ""


def layout_assumptions_missing(base_arch: str) -> list[str]:
    """What the override needs that Odoo's layout no longer has (empty = all there)."""
    missing = [needed for needed in _LAYOUT_NEEDS if needed not in base_arch]
    try:
        root = ET.fromstring(base_arch)
    except ET.ParseError:
        return [*missing, "a parsable arch"]
    if len(root) == 0:  # the anchor, /*/*[1]
        missing.append("a first element")
    return missing


def _layout_view(client: Any, name: str, parent_id: int) -> dict | None:
    rows = client.call(
        "ir.ui.view",
        "search_read",
        domain=[
            ["name", "=", name],
            ["inherit_id", "=", parent_id],
            ["active", "in", [True, False]],
        ],
        fields=["arch_db", "active"],
        limit=1,
    )
    return rows[0] if rows else None


def _apply_layout_view(client: Any, detail: dict) -> None:
    """Our own inherited view; Odoo's layout itself is never written."""
    if detail["action"] in ("keep", "skip"):
        return
    if detail["action"] == "deactivate":
        client.call(
            "ir.ui.view", "write", ids=[detail["view_id"]], vals={"active": False}
        )
        return
    vals = {"arch": detail["arch"], "active": True}
    if detail["view_id"]:
        client.call("ir.ui.view", "write", ids=[detail["view_id"]], vals=vals)
        return
    client.call(
        "ir.ui.view",
        "create",
        vals_list=[
            {
                "name": detail["name"],
                "type": "qweb",
                "mode": "extension",
                "inherit_id": detail["parent_id"],
                **vals,
            }
        ],
    )


def create_key(client: Odoo, *, name: str) -> str:
    """The bridge's own key: Odoo only lets a user create keys for itself.

    Sets a random temporary password, logs in as the bridge, runs the
    identity check with the password in the context, creates the key, and
    scrambles the password again.
    """
    uid = client.call("res.users", "search", domain=[["login", "=", LOGIN]], limit=1)[0]
    password = secrets.token_urlsafe(24)
    client.call("res.users", "write", ids=[uid], vals={"password": password})
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def rpc(path: str, params: dict) -> Any:
        body = json.dumps(
            {"jsonrpc": "2.0", "method": "call", "params": params}
        ).encode()
        req = urllib.request.Request(
            client.url + path, data=body, headers={"Content-Type": "application/json"}
        )
        result = json.loads(opener.open(req, timeout=60).read())
        if "error" in result:
            raise SystemExit(
                f"{path}: {result['error'].get('data', {}).get('message') or result['error']}"
            )
        return result["result"]

    def kw(model: str, method: str, args: list, kwargs: dict | None = None) -> Any:
        return rpc(
            "/web/dataset/call_kw",
            {"model": model, "method": method, "args": args, "kwargs": kwargs or {}},
        )

    try:
        rpc(
            "/web/session/authenticate",
            {"db": client.db, "login": LOGIN, "password": password},
        )
        expires = (date.today() + timedelta(days=KEY_DAYS - 1)).isoformat()
        desc = kw(
            "res.users.apikeys.description",
            "create",
            [{"name": name, "expiration_date": expires}],
        )
        action = kw("res.users.apikeys.description", "make_key", [[desc]])
        if action.get("res_model") != "res.users.apikeys.show":
            action = kw(
                "res.users.identitycheck",
                "run_check",
                [[action["res_id"]]],
                {"context": {"password": password}},
            )
        key = action["context"]["default_key"]
    finally:
        client.call(
            "res.users",
            "write",
            ids=[uid],
            vals={"password": secrets.token_urlsafe(32)},
        )
    print(f"bridge key {name!r} created, expires {expires}")
    return key


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("command", choices=["plan", "create-key", "rotate-key"])
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument(
        "--production", action="store_true", help="allow a non-staging database"
    )
    parser.add_argument("--team-id", type=int, default=1)
    args = parser.parse_args()
    url, db, key = (
        os.environ["ODOO_URL"],
        os.environ["ODOO_DB"],
        os.environ["ODOO_ADMIN_KEY"],
    )
    guard_target(url, db, production=args.production)
    goat_url = validate_goat_url(os.environ["GOAT_URL"])
    client = Odoo(url, db, key)
    if args.command == "plan":
        steps = plan(
            client,
            team_id=args.team_id,
            goat_url=goat_url,
        )
        if not args.apply:
            for s in steps:
                print("DRYRUN", s.description)
            return
        apply(client, steps, team_id=args.team_id)
        return
    if not args.apply:
        print(f"DRYRUN would create a {KEY_DAYS}-day API key for {LOGIN}")
        return
    suffix = date.today().isoformat()
    new_key = create_key(client, name=f"goat-core-{suffix}")
    print(
        "Store this key in the ODOO_SUPPORT_API_KEY secret now; it is not shown again:"
    )
    print(new_key)
    if args.command == "rotate-key":
        print(
            "After the deploy picked it up, revoke the previous key in Odoo: "
            "Settings > Users > GOAT Support Bridge > Account Security."
        )


if __name__ == "__main__":
    main()
