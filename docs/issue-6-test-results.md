# Issue #6 validation — 25 October 2026

Two preparation variants were exercised:

| Base | Python 3.14 | Python 3.12 | Node frontend tests |
|---|---:|---:|---:|
| Merged #5 (`bf9abc3`) | 51 passed | 51 passed | 15 passed |
| #7 implementation (`b0eca0c`) | 67 passed | 67 passed | 25 passed |

#6 adds 16 backend checks and 10 frontend checks. Existing #5/#7 tests remain part of the relevant variant. No remote CI or live browser/socket result is claimed; Python 3.11 will run in the configured GitHub Actions matrix.

Backend coverage includes anonymous denial; separate role summaries/navigation; group scoping; cross-role API/page rejection; ignored client-supplied roles/IDs; empty groups; membership revocation; database-backed active counts; active peers limited to visible groups; instructor membership versus management; literal profile/group text; omission of password/session secrets; unavailable tools without links; optional folder capability; normal-mode sessions; and new/old asset availability.

Frontend coverage includes initialization gating; role/profile/navigation replacement; empty state; safe link destinations; literal text; old refresh versus account switching; clearing private data after failed refresh; disabled demo selection in normal mode; direct-role denial; and normal-text contrast. Python compilation and JavaScript syntax checks pass.

## Manual verification before Done

- [ ] Select Student/Instructor/Administrator and check the correct heading, navigation, tools, counts and groups.
- [ ] Nonmember shows no private groups; another role's direct page is denied.
- [ ] Account switching and refresh do not retain the previous account's data.
- [ ] Future features have clear unavailable states; displayed links work.
- [ ] If #7 is present, its group-folder workspace remains accessible at /access and its permissions still work.
- [ ] Layout is usable at narrow widths and the browser console has no application errors.
- [ ] Verify real login integration once the authentication module is available.
- [ ] Review, CI checks, merge and integrated verification are complete before #6 is Done.
