# Admin authority work — handover

Last updated: 2026-09-17. Covers the admin-over-staff feature set.

The distinction this feature rests on: **staff** are content people, **admin** is
staff plus oversight, **superuser** is admin plus the single extra power to edit
another staff record. Everywhere else in the codebase admin and superuser are
treated as the same thing, and `SERVICE_INTERNAL/permissions.py::admin_only()`
already returns True for both. Do not change that helper.

---

## Ground rules, read before touching anything

- **No `makemigrations`, no `migrate`.** Every field this feature needs
  (`tribute_bio`, `last_promotion`, `get_blog_notification`, `role`,
  `Auth.is_active`) already exists in both the model and `db.sqlite3`. Note that
  `tribute_bio` and `last_promotion` are **in `STAFF/models.py` and in the DB
  table but absent from every file in `STAFF/migrations/`**. That is a
  pre-existing drift the owner is aware of. Leave it alone; running
  `makemigrations` will generate a migration that then fails to apply.
- **No new packages.** The project runs on Django + DRF + whitenoise +
  python-dotenv. Nothing else was added and nothing else is needed.
- **Never create a superuser from any view.** Account creation tops out at
  `is_admin=True`. Superuser is granted only through the owner's private
  endpoint in the `_` app. Do not touch, extend or document that path.
- **Never add a delete action** to any staff-facing admin screen. Suspension is
  the ceiling. This was an explicit instruction.
- The project is developed on Windows; most files use CRLF. Match the line
  endings of the file you are editing.
- Templates in `HOME` live under `HOME/templates/HOME/` with an **uppercase**
  folder name, and `HOME/views.py` now references them as `"HOME/..."`. Keep new
  references uppercase. `auth/` and `blog/` folders are genuinely lowercase.

---

## What is already done

### Fixes applied

| # | Fix |
|---|---|
| 1 | `profile.html` newsletter label now reads "Alert / Receiving login alert", matching the `receive_email_login_alert` field the view actually writes. View logic untouched. |
| 2 | All seven `render()` template paths in `HOME/views.py` uppercased to `HOME/...`. |
| 3 | `ADMIN` app registered in `INSTALLED_APPS`, given `urls.py` with `app_name = "control"`, mounted at `/control/`. |
| 4 | `debug_auth_check.py` deleted from the project root. |

Known and deliberately **not** fixed, per the owner: the AJAX JSON in
`ProfileBookmarksView`, `ProfileHistoryView` and `ProfileCommentsView` returns
`"url": f"/blog/{id}/"` while blog URLs are mounted at `/story/`, so those links
404 after a page change. Server-rendered rows use `{% url %}` and work. Leave it.

### `SERVICE_INTERNAL/config.py` — `StaffConfig`

Single source of truth for staff choice lists. Reads `STAFF.models.STAFF_ROLE`
lazily, so editing that tuple updates every role dropdown project-wide.

- `StaffConfig.role_choices()` — assignable roles, `PROTECTED_ROLES` filtered out
- `StaffConfig.role_choices(include_protected=True)` — everything, for labelling
- `StaffConfig.gender_choices()`, `StaffConfig.role_label(value)`
- `StaffConfig.PROTECTED_ROLES = {"FOUNDER"}` — never assignable from any view

It is **not** a context processor. Views pass it into context where needed, so
it costs nothing on pages that do not use it. Keep it that way.

### Staff directory panel (`profile.html`)

Sits at the very **top** of `<main class="profile-main">`, above the staff
dashboard, published stories, bookmarks and history. Admin and superuser only.
Five per page, `Open` link only, no delete. Rows read
`Authority • Role • Email`, plus `Suspended` when the account is inactive.

An account with no `StaffProfile` shows the name as **`NO USERNAME`** and
`No staff profile` in place of the role, so missing records are easy to spot.
The `.staff-directory-list` class drops the bold treatment so names render in
the plain body font.

Pagination reuses the existing `PROFILE_LISTS` machinery in `interactions.js`
(a `staff` entry plus `data-staff-page-btn` on the delegate). **Any new
paginated panel should do the same rather than write fresh pagination code.**

### Staff detail page — `/control/staff/<id>/`

Full page, admin and superuser only, non-staff IDs 404.

Read only for everyone: full name, gender, socials, speciality, bio, joined,
last promotion, and published news paginated five per page with an `Open` link.

**Deliberately absent, and must stay absent:** reading history, bookmark
history, profile image URL, newsletter preference. These are the staff member's
own settings and no admin overrides them from here.

Read and write, **superuser only**, an admin sees these disabled with a
"read only" notice:

- `tribute_bio` — the admin team's note about the staff member, distinct from
  their own bio
- role dropdown — options come from `StaffConfig.role_choices()`; a change
  stamps `last_promotion` with today; setting the same role again is a no-op and
  does **not** bump the date; Founder is rejected server side
- account status toggle — flips `Auth.is_active`; suspending calls
  `_drop_sessions_for()` and ends every session the account holds immediately;
  self-suspension returns 400; it never deletes an account

An account with no `StaffProfile` renders the page but every write returns 409.

### Files touched so far

```
NoName/settings.py                       INSTALLED_APPS += 'ADMIN'
NoName/urls.py                           path('control/', include("ADMIN.urls"))
SERVICE_INTERNAL/config.py               + StaffConfig
HOME/views.py                            template path casing; staff directory context
HOME/templates/HOME/profile.html         label fix; staff directory panel at top of main
HOME/static/home/js/interactions.js      staff + staffPublished list configs; record write controls
HOME/static/home/css/profile.css         .staff-directory-list, .staff-record-* (appended)
ADMIN/views.py                           NEW
ADMIN/urls.py                            NEW
ADMIN/templates/ADMIN/staff_detail.html  NEW
debug_auth_check.py                      DELETED
```

### URL map

| Name | Path | Method | Who |
|---|---|---|---|
| `control:staff_directory` | `/control/staff/` | GET | admin+ |
| `control:staff_detail` | `/control/staff/<id>/` | GET | admin+ |
| `control:staff_published` | `/control/staff/<id>/published/` | GET | admin+ |
| `control:staff_tribute` | `/control/staff/<id>/tribute/` | POST | superuser |
| `control:staff_role` | `/control/staff/<id>/role/` | POST | superuser |
| `control:staff_status` | `/control/staff/<id>/status/` | POST | superuser |

---

## What still needs doing

### TODO 1 — Admin edits their own role, on their own profile page

**Not the detail page.** An admin has read-only access to *other* people's
records, but may change **their own** role freely, and every change stamps
`last_promotion` with today.

- Add a role `<select>` to the existing staff block in `profile.html`, near the
  other own-profile fields, rendered only when `is_admin_user` is true.
- Populate it from `StaffConfig.role_choices()` passed in from `ProfileView`.
  Do not hard code the options.
- New POST endpoint. `ADMIN/urls.py` is the right home since this is an admin
  privilege; something like `control:own_role`. It must act on
  `request.user`'s own `StaffProfile` only, never take a target ID.
- Reject any value outside `StaffConfig.role_choices()`, which already excludes
  Founder.
- On change, set `role` and `last_promotion = timezone.localdate()`, and
  `save(update_fields=[...])`.
- Non-admin staff must not see this control and must get a 403 from the
  endpoint.

Reuse the feedback pattern from the detail page write controls in
`interactions.js` rather than inventing a new one.

### TODO 2 — Blog notification toggle, for staff and admin

The field is `StaffProfile.get_blog_notification` (post-view reminders).

- Render a toggle **directly underneath** the existing Alert / login-alert
  toggle in the `profile.html` aside. Staff and admin only; plain members have
  no `StaffProfile` and must not see it.
- Copy the markup of the existing toggle exactly: `button.toggle-switch`,
  `is-on` class, `aria-pressed`, `span.toggle-knob`.
- New POST endpoint flipping the boolean and returning
  `{detail, enabled, status}`, matching `ProfileNewsletterToggleView`'s response
  shape so the existing JS handler pattern carries over.
- This is a staff-level setting, not an admin power, so it belongs in
  `HOME/views.py` next to the other profile toggles, not in `ADMIN`.
- Handle the case where the staff member somehow has no `StaffProfile`: do not
  crash, return a clear message.

### TODO 3 — "Log out all sessions"

- Button at the **bottom of the aside** in `profile.html`, below every existing
  setting block. Available to any signed-in user, not just staff.
- Deletes **every** session belonging to the user, the current one included, so
  they are signed out and land on the login page.
- `ADMIN/views.py::_drop_sessions_for(account)` already does exactly this walk.
  **Move it somewhere shared rather than duplicating it** — `SERVICE_INTERNAL`
  is the natural home — then have both callers import it. Do not leave two
  copies.
- Confirm before firing; this is destructive from the user's point of view.
- After the POST succeeds the JS should redirect to login rather than leaving a
  dead page behind.
- The session walk decodes every row in the table. Fine at current scale, worth
  a comment noting it will need an index-backed approach if the site grows.

### TODO 4 — "Add staff" button and creation page

- Button to the **left** of the existing `+ NeWs` link in the `profile-header-bar`
  of `profile.html`. Admin and superuser only.
- Opens a **full page form**, not a modal. Put it in `ADMIN` as
  `control:staff_create`.
- Fields: email, password **prefilled with `NewStaff`** (the staff member
  changes it later themselves), plus whatever the form needs to build a usable
  `StaffProfile`. Ask the owner before adding fields beyond full name, gender
  and role.
- Role options from `StaffConfig.role_choices()`. Founder is excluded already.
- An admin may create another **admin**. **Nothing here may ever set
  `is_superuser=True`**, regardless of input. Whitelist the flags you set rather
  than reading them from POST data.
- Create the `Auth` row and its `StaffProfile` together; an account without a
  profile is exactly the broken state the directory panel now flags.
- Reject duplicate emails with a readable error, not a 500.
- Check `AUTHENTICATION/views.py::RegisterView` first and follow its
  normalisation and hashing, do not hand-roll password handling.

---

## How to verify without a browser

Django, DRF and whitenoise must be installed. `python manage.py check` should be
clean. The app can then be driven with `django.test.Client` against the real
`db.sqlite3`.

**If you mutate a record while testing, capture the original values first and
write them back afterwards.** This database has the owner's real data in it.
`TMP_PUB@X.COM` appears to be a throwaway account and is the safest target.

To exercise the plain-admin path there is currently **no admin-but-not-superuser
account in the database**. Rather than creating one, build an unsaved
`Auth(is_admin=True, is_superuser=False)` instance, assign it a fake `pk`, and
drive the view through `RequestFactory` with `request.user` set to it. That
exercises the real permission branch without writing to the DB.
