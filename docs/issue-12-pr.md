Implement material viewing and downloading for authorized study groups. The new `/materials` library supports group filtering, paging, safe text/code, PDF and raster previews, and native streaming downloads with original filenames. Direct file URLs, HEAD, and range requests all enforce session, role, and group access.

Files stay in private storage outside static assets. The server rejects unsafe paths/symlinks, missing or incomplete files, and unsafe inline formats; responses use bounded streaming, safe filename/type headers, and no-store caching. Demo fixtures provide PDF, PNG, code, DOCX, and a private resource for review alongside the merged #7 folder feature. Folder routes, frontend, schema, and tests are preserved after incorporating latest main.

Validation: 75 Python tests pass on 3.12 and 3.14; 30 frontend tests pass, including folder/material coexistence coverage. Python compilation and JavaScript syntax checks pass. Sample PDF text was read with PDFKit; PNG checksums/pixels and DOCX archive were checked. CI retains pinned actions and the Python 3.11/3.12 matrix. Live HTTP checks pass for authenticated folder creation, downloads, HEAD/ranges, and private/nonmember denial. Interactive browser checks and updated remote CI remain pending.

Integration: real credential login, membership management, uploads, upload validation, and folder association remain their separate modules. Dashboard #6 remains separate; merged #7 folders are retained. The direct `/materials` page works alongside merged #5/#7; the dashboard action can be connected after #6 merges.

Closes #12
