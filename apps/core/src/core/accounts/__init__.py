"""Sign-ups, organizations and trials as Odoo contacts (SaaS with billing only).

Odoo's side is the goat_accounts module: GOAT calls its server action
"GOAT: accounts" as the bridge user, with the operation in the context:

- sign_up: a user with a verified email, on their first request. Odoo finds
  or creates their contact; GOAT keeps its id in user.odoo_contact_id.
- start_trial: they created an organization with a trial. Odoo finds or
  creates the company (organization.odoo_company_id), the person goes under
  it with the trial tag, and the trial's dates are set; the campaign starts.
- join: an invited member joined an organization.

Nothing here blocks GOAT: the calls run after the request's own work is
committed, in the background, and a failure is logged only. A user without
odoo_contact_id is reported again on a later request (at most every
RETRY_SECONDS per process), so Odoo being down delays the sync, nothing more.
Off without billing or without ODOO_BILLING_API_KEY (settings.accounts_sync_enabled).
"""

from core.accounts.sync import report_join, report_sign_up, report_trial

__all__ = ["report_join", "report_sign_up", "report_trial"]
