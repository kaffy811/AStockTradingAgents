from __future__ import annotations

import os


os.environ.setdefault(
    "CORS_ORIGINS",
    "["
    '"http://localhost:3000",'
    '"http://localhost:3001",'
    '"http://localhost:3002",'
    '"http://localhost:5173",'
    '"http://localhost:5174",'
    '"http://127.0.0.1:3000",'
    '"http://127.0.0.1:3001",'
    '"http://127.0.0.1:3002",'
    '"http://127.0.0.1:5173",'
    '"http://127.0.0.1:5174"'
    "]",
)
