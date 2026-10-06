"""Python code of the Odoo server action "GOAT: post message as ticket participant".

Runs inside Odoo (safe_eval) when the GOAT Support Bridge calls
ir.actions.server/run. It is the only place the bridge acts with elevated
rights, so everything is checked first. Ops (context "goat_op"):
  contact — create one individual customer contact (name, email, language,
            optionally under a customer company); no ticket involved; refuses
            odd input and the email of (former) staff
  post    — one customer-facing message (text and/or files) as a participant
  rate    — create/update that participant's rating on a solved ticket
  staff   — which of the given partners are or were staff (read only)
  agent   — the partner of the ticket's assigned agent, also before they have
            written anything (read only; the bridge cannot read res.users)
The bridge itself can only read res.partner: contacts are created here so a
leaked bridge key cannot edit existing partners (e.g. redirect invoices).
"""

import textwrap

# Plain text in (variable `body`), safe HTML out (variable `html`). Only & < > are
# escaped: the result is used as text-node content, where quotes are harmless, and
# Odoo's HTML sanitizer stores quotes unescaped, so escaping them would make the
# duplicate guard below compare two different strings. The same source is embedded
# in the action code and exec'd by the tests.
ESCAPE_CODE = r"""
esc = body.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
esc = esc.replace('\r\n', '\n').replace('\r', '\n')
paras = [p.strip('\n') for p in esc.split('\n\n') if p.strip()]
html = ''.join('<p>' + p.replace('\n', '<br>') + '</p>' for p in paras)
""".lstrip("\n")

# Staff = a partner with an internal user, active or archived, or with an employee
# record, active or archived. Odoo recomputes partner_share from *active* users only,
# so an archived staff user's partner turns into a customer-side partner, and a
# deleted user leaves a partner without any user at all; the employee record usually
# outlives both. Defines `staff_ids(ids) -> set of partner ids`; exec'd by the tests.
STAFF_CODE = r"""
def staff_ids(ids):
    partners = env['res.partner'].sudo().with_context(active_test=False).browse([int(i) for i in ids]).exists()
    staff = set(partners.filtered(lambda p: not p.partner_share or any(not u.share for u in p.user_ids)).ids)
    if 'hr.employee' in env:
        employees = env['hr.employee'].sudo().with_context(active_test=False).search([('work_contact_id', 'in', partners.ids)])
        staff |= set(employees.mapped('work_contact_id').ids)
    return staff
""".lstrip("\n")

# Input of the "contact" op. Defines `contact_input_error(name, email) -> str or None`:
# a short reason when the name or email is not acceptable. The email is a plain
# addr-spec subset: one @, a local part of atext characters and single dots, a
# domain of letter/digit/hyphen labels with at least one dot. No control characters
# (CR, LF, tab...) anywhere: Odoo puts both into mail headers. Exec'd by the tests.
CONTACT_CHECK_CODE = r"""
def contact_input_error(name, email):
    # Plain loops only: Odoo's safe_eval refuses closures (a generator or lambda
    # that reads a local of this function).
    if not name or len(name) > 200 or len(email) > 254:
        return 'invalid contact'
    for c in name + email:
        if ord(c) < 32 or 127 <= ord(c) < 160:
            return 'invalid contact'
    if email.count('@') != 1:
        return 'invalid contact'
    local, domain = email.split('@')
    if not local or len(local) > 64:
        return 'invalid contact'
    atext = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!#$%&\'*+/=?^_`{|}~-')
    for part in local.split('.'):
        if not part or not set(part) <= atext:
            return 'invalid contact'
    label_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-')
    labels = domain.split('.')
    if len(labels) < 2:
        return 'invalid contact'
    for label in labels:
        if not label or len(label) > 63 or not set(label) <= label_chars or label[0] == '-' or label[-1] == '-':
            return 'invalid contact'
    return None
""".lstrip("\n")

ACTION_CODE_TEMPLATE = """
if {group_id} not in env.user.all_group_ids.ids:
    raise UserError("not allowed")
ctx = env.context
root = env.ref('base.user_root')
{staff_code}{contact_check_code}clean = {{'lang': ctx.get('lang') or 'en_US'}}
op = ctx.get('goat_op') or 'post'
if op == 'contact':
    name = str(ctx.get('goat_name') or '').strip()
    email = str(ctx.get('goat_email') or '').strip()
    lang = ctx.get('goat_lang') or 'en_US'
    problem = contact_input_error(name, email)
    if problem:
        raise UserError(problem)
    if lang not in ('en_US', 'de_DE'):
        raise UserError("invalid language")
    # Never a customer contact with a staff member's (or former staff's) email: replies
    # to it would reach staff, and GOAT would link that user to it.
    same_email = env['res.partner'].sudo().with_context(active_test=False).search([('email_normalized', '=', email.lower())])
    if staff_ids(same_email.ids):
        raise UserError("email belongs to staff")
    vals = {{'name': name, 'email': email, 'lang': lang, 'is_company': False, 'type': 'contact'}}
    parent_id = int(ctx.get('goat_parent_id') or 0)
    if parent_id:
        partners = env['res.partner'].sudo().with_context(active_test=False)
        parent = partners.browse(parent_id).exists()
        # A customer company only: not one of our own companies, no staff (current or former) in it.
        if not parent or not parent.is_company or not parent.partner_share or parent.ref_company_ids or staff_ids(partners.search([('id', 'child_of', parent.id)]).ids):
            raise UserError("invalid parent company")
        vals['parent_id'] = parent.id
    contact = env['res.partner'].with_user(root).with_context(clean).create(vals)
    log('GOAT bridge created contact %s' % contact.id)
    action = {{'type': 'ir.actions.act_window_close', 'goat_contact_id': contact.id}}
elif op == 'staff':
    ids = list(ctx.get('goat_partner_ids') or [])
    if len(ids) > 1000:
        raise UserError("too many partners")
    action = {{'type': 'ir.actions.act_window_close', 'goat_staff_ids': sorted(staff_ids(ids))}}
elif op == 'agent':
    ticket = env['helpdesk.ticket'].browse(int(ctx.get('active_id') or 0)).exists()
    if not ticket or ticket.team_id.id != {team_id}:
        raise UserError("unknown ticket")
    action = {{'type': 'ir.actions.act_window_close', 'goat_agent_partner_id': ticket.sudo().user_id.partner_id.id or False}}
elif op not in ('rate', 'post'):
    raise UserError("unknown operation")
else:
    ticket = env['helpdesk.ticket'].browse(int(ctx.get('active_id') or 0)).exists()
    if not ticket or ticket.team_id.id != {team_id}:
        raise UserError("unknown ticket")
    author = env['res.partner'].browse(int(ctx.get('goat_author_id') or 0)).exists()
    participants = ticket.sudo().partner_id | ticket.sudo().message_partner_ids
    # Never staff, also not former staff (archived or deleted user, see STAFF_CODE).
    if not author or author.is_company or not author.partner_share or staff_ids(author.ids) or author not in participants:
        raise UserError("author is not a customer-side participant of this ticket")
if op == 'rate':
    value = int(ctx.get('goat_rating') or 0)
    if value not in (1, 3, 5):
        raise UserError("invalid rating")
    if ticket.stage_id.with_context(lang='en_US').name != 'Solved':
        raise UserError("ticket is not solved")
    feedback = (ctx.get('goat_feedback') or '')[:2000]
    ratings = env['rating.rating'].with_user(root).with_context(clean)
    existing = ratings.search([('res_model', '=', 'helpdesk.ticket'), ('res_id', '=', ticket.id), ('partner_id', '=', author.id)], limit=1)
    vals = {{'rating': value, 'feedback': feedback, 'consumed': True}}
    if existing:
        existing.write(vals)
        rating_id = existing.id
    else:
        model_id = env['ir.model'].sudo().search([('model', '=', 'helpdesk.ticket')], limit=1).id
        vals.update({{'res_model_id': model_id, 'res_id': ticket.id, 'partner_id': author.id, 'rated_partner_id': ticket.sudo().user_id.partner_id.id}})
        rating_id = ratings.create(vals).id
    log('GOAT bridge rated ticket %s as partner %s: %s' % (ticket.id, author.id, value))
    action = {{'type': 'ir.actions.act_window_close', 'goat_rating_id': rating_id}}
elif op == 'post':
    body = ctx.get('goat_body_text') or ''
    if len(body) > 50000:
        raise UserError("oversized body")
    atts = env['ir.attachment'].browse([int(a) for a in (ctx.get('goat_attachment_ids') or [])]).exists()
    if not body.strip() and not atts:
        raise UserError("empty message")
    if any(a.create_uid != env.user or a.res_model != 'helpdesk.ticket' or a.res_id != ticket.id for a in atts):
        raise UserError("attachments must be uploaded by the bridge to this ticket")
    # Plain text in, safe HTML out (see ESCAPE_CODE).
{escape_code}    since = datetime.datetime.now() - datetime.timedelta(seconds=60)
    recent = env['mail.message'].sudo().search([('model', '=', 'helpdesk.ticket'), ('res_id', '=', ticket.id), ('author_id', '=', author.id), ('message_type', '=', 'comment'), ('date', '>=', since)], order='id desc', limit=1)
    if recent and not atts and str(recent.body or '') == html:
        msg = recent
    else:
        msg = ticket.with_user(root).with_context(clean).message_post(
            body=html, body_is_html=True, message_type='comment', subtype_xmlid='mail.mt_comment',
            author_id=author.id, attachment_ids=atts.ids,
        )
        log('GOAT bridge posted message %s on ticket %s as partner %s' % (msg.id, ticket.id, author.id))
    action = {{'type': 'ir.actions.act_window_close', 'goat_message_id': msg.id}}
"""


def action_code(group_id: int, team_id: int) -> str:
    return ACTION_CODE_TEMPLATE.format(
        group_id=int(group_id),
        team_id=int(team_id),
        escape_code=textwrap.indent(ESCAPE_CODE, "    "),
        staff_code=STAFF_CODE,
        contact_check_code=CONTACT_CHECK_CODE,
    )
