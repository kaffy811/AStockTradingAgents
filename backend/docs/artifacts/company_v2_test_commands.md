# CompanyV2 Test Commands

## Standard Commands

Run backend tests from the repository root:

```bash
pytest -q
```

The root `pytest.ini` limits default collection to `backend/tests` and sets `pythonpath=backend`, so legacy root-level Playwright scripts are not collected as unit tests.

Run backend tests from `backend/`:

```bash
cd backend
pytest -q
```

Run frontend unit tests:

```bash
cd frontend
npm run test
```

Run frontend build:

```bash
cd frontend
npm run build
```

## Optional E2E

Playwright/browser validation is optional and requires frontend/backend services plus Playwright browsers:

```bash
cd frontend
npx playwright test
```

Legacy `test_stock_detail.py` is treated as a manual/optional Playwright script and is not part of default pytest collection.

## Expected CI Split

- Backend unit/regression: `pytest -q`
- Frontend unit/source tests: `npm run test`
- Frontend production build: `npm run build`
- E2E/manual browser acceptance: optional Playwright job
