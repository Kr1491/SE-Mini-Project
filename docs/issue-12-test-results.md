# Issue #12 — verification

## Automated results

- Python 3.12 and 3.14: **58 tests passed** on each interpreter, including the 35 existing authorization/review tests and 23 material tests.
- Node.js: **20 tests passed**, including five existing access-console tests and 15 material-interface tests.
- Python compileall and `node --check` for both JavaScript files passed.
- The generated sample PDF was parsed by macOS PDFKit as one page containing the expected text. PNG chunk checksums and decoded pixel length passed; the DOCX archive passed ZIP validation and contained its expected document text.

Python tests use the real HTTP handler/parser with in-memory connections and temporary SQLite/files. They check anonymous/non-member denial, owner/member/admin catalogs, private direct URLs, forged role/MIME data, group filtering/pagination validation, correct file bytes/dispositions, HEAD, ranges, missing/incomplete files, traversal, symlinks, FIFO/directory rejection, insecure storage, Unicode/control filename handling, bounded chunks, interrupted transfer behavior, membership revocation, real versus demo session provenance, fixture conflict refusal, and private permissions.

Frontend tests execute `materials.js` with a simulated DOM/fetch. They cover startup gating, normal-mode authentication feedback, literal text rendering, download-only files, group/paging requests, stale catalogs/previews/download checks, closing previews, account switches, text size limits, PDF/image endpoint selection, successful HEAD before native downloads, 401/403/404 feedback, and clearing expired-session data.

A live server/browser check is pending because this execution environment blocks listening sockets. These tests do not replace checking the browser's native PDF viewer, file download UI, keyboard interaction, and narrow-screen layout. Python 3.11 is configured in CI with 3.12; no local 3.11 interpreter was available. Remote CI results are pending the user's push.

## Manual checks before review/merge

Run `python3 server.py --demo --port 8003` and open `http://127.0.0.1:8003/materials`.

1. Select Student. Four materials should appear across Software Engineering and Database Systems. Filter each group and verify its two resources.
2. View the PDF, PNG, and Python source. Code must appear as literal readable text. DOCX should say Download only. Download all four and open the saved files; names and contents should match their displayed resources. If the browser does not embed PDFs, use Download.
3. Select Student without groups. The list should clear and show an empty state. Refreshing a copied direct file URL should deny access.
4. Select Administrator. Five resources should appear, including Private research notes. Copy that file's view URL, switch to Student, and refresh it: expect 403. Return to `/materials` to continue.
5. Switch accounts while requests are pending using browser network throttling. Old previews/lists should not reappear; a pending previous-account download check must not start a download under the next account.
6. Close and reopen previews, use keyboard Tab/Escape, and check at mobile width. Navigate through the Workspace link and back to the material library. Normal mode should hide all sample selectors and require a real session.
7. After teammates' modules merge, perform a real login → authorized group → upload → refresh library → preview/download journey. Verify the uploaded byte size and denied access from an unrelated account. This integration journey is pending those modules; fixtures alone do not establish its success.

Keep #12 In progress during local verification. Open its PR and put it In review, leaving #6/#7 In review until each is reviewed, merged, and verified.
