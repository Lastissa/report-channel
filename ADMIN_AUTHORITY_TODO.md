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
| 5 | `LoginView.post` no longer 500s on a wrong email (`None.check_password`) or on the non AJAX wrong-password path (undefined `return_to`). Both now return the invalid credentials response. The login page also reloads itself when the submit response is not JSON, which is the stale CSRF pair case that used to need a manual refresh. |
| 6 | `.profile-summary` no longer viewport clamps (`max-height` + `overflow: hidden` removed, sticky dropped). That clamp hid the bottom of the staff record aside on desktop and pushed the logout-all block behind the following cards on mobile. |

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
SERVICE_INTERNAL/sessions.py             NEW, shared drop_sessions_for walk
HOME/views.py                            template path casing; staff directory context; blog notification toggle; logout-all view; role context
HOME/urls.py                             + profile_blog_notification_toggle, profile_logout_all
HOME/templates/HOME/profile.html         label fix; staff directory panel; story view alert toggle; own role select; logout-all block; + Staff link
HOME/static/home/js/interactions.js      staff + staffPublished list configs; record write controls; per-toggle labels; own role / logout-all / add staff handlers
HOME/static/home/css/profile.css         .staff-directory-list, .staff-record-*, header actions, logout-all, staff-create (appended)
ADMIN/views.py                           NEW
ADMIN/urls.py                            NEW, + staff_create, own_role
ADMIN/templates/ADMIN/staff_detail.html  NEW, toggle-knob renamed to toggle-thumb (had no CSS)
ADMIN/templates/ADMIN/staff_create.html  NEW
debug_auth_check.py                      DELETED
```

### URL map

| Name | Path | Method | Who |
|---|---|---|---|
| `control:staff_directory` | `/control/staff/` | GET | admin+ |
| `control:staff_create` | `/control/staff/new/` | GET, POST | admin+ |
| `control:staff_detail` | `/control/staff/<id>/` | GET | admin+ |
| `control:staff_published` | `/control/staff/<id>/published/` | GET | admin+ |
| `control:staff_tribute` | `/control/staff/<id>/tribute/` | POST | superuser |
| `control:staff_role` | `/control/staff/<id>/role/` | POST | superuser |
| `control:staff_status` | `/control/staff/<id>/status/` | POST | superuser |
| `control:own_role` | `/control/me/role/` | POST | admin+ (acts on self only) |
| `home:profile_blog_notification_toggle` | `/profile/settings/blog-notification/` | POST | staff+ |
| `home:profile_logout_all` | `/profile/settings/logout-all/` | POST | any signed-in user |

---

## What still needs doing

Nothing from the four-TODO list. All four shipped on 2026-09-17, verified
against the real `db.sqlite3` with `django.test.Client` plus `RequestFactory`
fake users for the plain-admin branch (41/41 checks passed; every mutated
record was captured and restored).

### DONE — TODO 1, admin's own role on their own profile

- Role `<select>` added to the staff form in `profile.html`, rendered only for
  `is_admin_user`, options from `StaffConfig.role_choices()` passed in by
  `ProfileView` (`role_choices` / `protected_roles` context keys).
- `control:own_role` (`/control/me/role/`, POST) acts on `request.user` only,
  never takes a target id. Values outside `StaffConfig.role_choices()` are
  rejected (Founder included); same-role is a "Role unchanged" no-op; every
  real change stamps `last_promotion = timezone.localdate()` with
  `save(update_fields=["role", "last_promotion"])`. Plain staff get 403, no
  profile gets 409.
- The role select posts to its own endpoint via its own button; the staff
  form's "Save changes" never carries role.

### DONE — TODO 2, story view alert toggle

- Toggle rendered directly under the Alert toggle in the `profile.html` aside,
  shown only when `is_staff_user and profile`. Markup copies the existing
  toggle: `button.toggle-switch`, `is-on`, `aria-pressed`, `span.toggle-thumb`.
  (The handover said `toggle-knob`, but the real existing toggle uses
  `toggle-thumb`; `staff_detail.html` was still using `toggle-knob`, which had
  no CSS at all, so its knob rendered invisible. Both now use `toggle-thumb`.)
- `home:profile_blog_notification_toggle` (`/profile/settings/blog-notification/`,
  POST) lives in `HOME.views` next to the other profile toggles, returns
  `{detail, enabled, status}`, and answers 409 with a clear message when the
  staff member has no `StaffProfile`. 403 for anyone without staff access.
- The shared JS toggle handler now reads per-toggle `data-on-text` /
  `data-off-text` labels instead of hard coding "Receiving updates", so both
  toggles keep correct copy through optimistic flips and rollbacks.

### DONE — TODO 3, log out all sessions

- The session walk moved to `SERVICE_INTERNAL/sessions.py::drop_sessions_for`
  (with the growth caveat comment); `ADMIN.views` and `HOME.views` both import
  it. No duplicate copy left.
- Button sits at the bottom of the `profile.html` aside for every signed-in
  user, confirms before firing, and POSTs to
  `home:profile_logout_all` (`/profile/settings/logout-all/`). The view deletes
  every session, calls `django.contrib.auth.logout`, and returns JSON with
  `redirect_to`; the JS redirects to the login page so no dead page is left.

### DONE — TODO 4, add staff

- `+ Staff` link to the left of `+ NeWs` in the `profile-header-bar`, admin
  and superuser only, opens the full page `control:staff_create`
  (`/control/staff/new/`).
- Fields per the owner's decision: email, password prefilled `NewStaff`, full
  name, gender, role, plus an "also grant admin access" checkbox. Nothing
  else; the new staff member fills in the rest themselves.
- `Auth` and `StaffProfile` rows are created together in one transaction.
  Flags are whitelisted (`is_staff` always, `is_admin` only from the
  checkbox); nothing on the page can set `is_superuser`. Password handling
  goes through `AuthManager.create_staff` → `set_password`, matching
  `RegisterView`. Duplicate email returns a readable 400, Founder is rejected,
  and non-admins are redirected away from the page entirely.
- Success redirects to the new staff member's `/control/staff/<id>/` record.

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
