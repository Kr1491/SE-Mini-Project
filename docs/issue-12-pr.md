Implement material viewing and downloading for authorized study groups. The new `/materials` library supports group filtering, paging, safe text/code, PDF and raster previews, and native streaming downloads with original filenames. Direct file URLs, HEAD, and range requests all enforce session, role, and group access.

Files stay in private storage outside static assets. The server rejects unsafe paths/symlinks, missing or incomplete files, and unsafe inline formats; responses use bounded streaming, safe filename/type headers, and no-store caching. Demo fixtures provide PDF, PNG, code, DOCX, and a private resource so this can be reviewed independently of pending dashboard/folder PRs.

Validation: 58 Python tests pass on 3.12 and 3.14; 20 frontend tests pass. Python compilation and JavaScript syntax checks pass. Sample PDF text was read with PDFKit; PNG checksums/pixels and DOCX archive were checked. CI retains pinned actions and the Python 3.11/3.12 matrix. Live browser checks and remote CI remain pending your execution.

Integration: real credential login, membership management, uploads, upload validation, and folder association remain their separate modules. Dashboard #6 and folders #7 are not included. The direct `/materials` page works with merged #5; the dashboard action can be connected after #6 merges.

Closes #12
