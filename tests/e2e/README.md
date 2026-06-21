# End-to-End Tests

These tests use Playwright to simulate a real user interacting with the VeriClaim React dashboard in a headless browser.

## Prerequisites

Before running the E2E tests, you need both the backend and frontend servers running. You can run these in separate terminal windows.

**1. Start the FastAPI Backend (Terminal 1)**
```bash
uv run uvicorn app.main:app --port 8000
```

**2. Start the React Frontend (Terminal 2)**
```bash
cd dashboard
npm run dev
```

**3. Run the Tests (Terminal 3)**
Ensure the Playwright browsers are installed first:
```bash
uv run playwright install
```

Run the pytest E2E suite:
```bash
uv run pytest tests/e2e/test_dashboard_e2e.py
```

To see the browser while the test runs (headed mode):
```bash
uv run pytest tests/e2e/test_dashboard_e2e.py --headed
```
