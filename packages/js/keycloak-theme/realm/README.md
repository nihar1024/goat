# Sign-up fields of the GOAT realm

`user-profile.json` is the realm's declarative user profile (Keycloak 22,
feature `declarative-user-profile`): what the sign-up page asks for. It lived
only in the live realm before; this file is the source now.

One step: first name, last name, email, password, the terms (required, stored
as the time they were accepted) and the newsletter (optional, stored as the
time of consent, empty without). Country, profession, domain and phone are no
longer asked: existing users keep their old values as unmanaged attributes,
nothing reads them. Students apply separately for a longer trial.

## Applying it to a realm

1. Realm settings → User profile → JSON editor: paste `user-profile.json`, save.
2. Clients → `goat` → Client scopes → the dedicated scope → Add mapper → By
   configuration → User Attribute: name `newsletter`, user attribute
   `subscribe_to_newsletter`, token claim name `newsletter`, claim JSON type
   String, added to the ID token and access token. GOAT core reads the claim when
   it first sees the user (`user.newsletter_subscribe`) and passes the consent on
   to Odoo.
3. Realm settings → Login: "User registration" and "Verify email" on (SaaS only;
   self-hosted realms keep registration off).

The page itself is `src/login/pages/RegisterUserProfile.tsx`; `kcContext.ts`
mocks it for `pnpm dev` with these attributes.
