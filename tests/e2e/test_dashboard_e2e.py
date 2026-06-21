import os
import pytest
from playwright.sync_api import Page, expect

# E2E Tests for the React Dashboard
# Assumes the backend is running on http://localhost:8000
# and the frontend is running on http://localhost:5173

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000/dashboard")

@pytest.fixture(scope="session", autouse=True)
def setup_e2e_db():
    """Ensure the database has an agent for E2E testing."""
    # We can rely on the existing test_claims_api setup or just test UI flows.
    # In a real E2E environment we would seed the DB here.
    pass

def test_login_and_view_claims(page: Page):
    """Test that an agent can log in and view the claim queue."""
    page.goto(FRONTEND_URL)
    
    # Check that we are redirected to the login page
    expect(page.locator("h1")).to_contain_text("VeriClaim Dashboard")
    
    # Enter credentials
    # In our local test db, we have agent1@vericlaim.com / password123
    page.fill('input[type="email"]', "agent1@vericlaim.com")
    page.fill('input[type="password"]', "password123")
    page.click('button[type="submit"]')
    
    # Should redirect to dashboard
    expect(page.locator("h2")).to_contain_text("Claim Queue")
    
    # Should display the table
    expect(page.locator("table")).to_be_visible()
    expect(page.locator("th").first).to_contain_text("ID")

def test_view_claim_detail(page: Page):
    """Test that clicking a claim opens the detail page."""
    page.goto(FRONTEND_URL)
    
    # Login again (since session might not persist depending on setup)
    page.fill('input[type="email"]', "agent1@vericlaim.com")
    page.fill('input[type="password"]', "password123")
    page.click('button[type="submit"]')
    
    # Wait for table to load
    page.wait_for_selector("tbody tr")
    
    # Click the first claim row
    page.click("tbody tr:first-child")
    
    # Should navigate to claim detail page
    expect(page.locator("h3").first).to_contain_text("Claim")
    expect(page.locator("h3:has-text('Evidence')")).to_be_visible()
