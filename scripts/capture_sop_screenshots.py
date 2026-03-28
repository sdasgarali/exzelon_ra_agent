"""Capture screenshots of all NeuraLeads AI Agent dashboard pages using Playwright.

Usage:
    python scripts/capture_sop_screenshots.py [--base-url URL] [--email EMAIL] [--password PASSWORD]

Saves screenshots to scripts/sop_screenshots/ directory.
"""
import os
import sys
import time
import argparse

from playwright.sync_api import sync_playwright

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT_DIR = os.path.join(SCRIPT_DIR, "sop_screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# Pages to capture (route_suffix, filename, description, wait_extra_ms)
PAGES = [
    # Login page (before auth)
    ("LOGIN", "01_login.png", "Login Page", 1000),
    # Dashboard pages (after auth)
    ("dashboard", "02_dashboard.png", "Dashboard", 2000),
    ("dashboard/leads", "03_leads.png", "Leads Page", 2000),
    ("dashboard/contacts", "04_contacts.png", "Contacts Page", 2000),
    ("dashboard/clients", "05_clients.png", "Clients Page", 2000),
    ("dashboard/validation", "06_validation.png", "Email Validation", 2000),
    ("dashboard/campaigns", "07_campaigns.png", "Campaigns", 2000),
    ("dashboard/outreach", "08_outreach.png", "Outreach", 2000),
    ("dashboard/inbox", "09_inbox.png", "Unified Inbox", 2000),
    ("dashboard/deals", "10_deals.png", "CRM Deals", 2000),
    ("dashboard/analytics", "11_analytics.png", "Analytics", 2000),
    ("dashboard/icp-wizard", "12_icp_wizard.png", "ICP Wizard", 2000),
    ("dashboard/templates", "13_templates.png", "Email Templates", 2000),
    ("dashboard/mailboxes", "14_mailboxes.png", "Mailboxes", 2000),
    ("dashboard/warmup", "15_warmup.png", "Warmup Engine", 2000),
    ("dashboard/pipelines", "16_pipelines.png", "Pipelines", 2000),
    ("dashboard/automation", "17_automation.png", "Automation", 2000),
    ("dashboard/users", "18_users.png", "User Management", 2000),
    ("dashboard/roles", "19_roles.png", "Roles & Permissions", 2000),
    ("dashboard/backups", "20_backups.png", "Data Backups", 2000),
    ("dashboard/settings", "21_settings.png", "Settings", 2000),
]


def capture_screenshots(base_url: str, email: str, password: str):
    """Capture screenshots of all pages."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1.5,
        )
        page = context.new_page()

        # 1) Capture login page
        print("Capturing login page...")
        page.goto(f"{base_url}/login", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1500)
        login_path = os.path.join(SCREENSHOT_DIR, "01_login.png")
        page.screenshot(path=login_path, full_page=False)
        print(f"  Saved: {login_path}")

        # 2) Login
        print(f"Logging in as {email}...")
        page.fill('input[type="email"], input[name="email"]', email)
        page.fill('input[type="password"], input[name="password"]', password)
        page.click('button[type="submit"]')

        # Wait for redirect to dashboard
        try:
            page.wait_for_url("**/dashboard**", timeout=15000)
        except Exception:
            # Maybe already on dashboard or different redirect
            page.wait_for_timeout(3000)

        page.wait_for_timeout(2000)
        print("  Login successful!")

        # 3) Capture each dashboard page
        for route, filename, description, wait_ms in PAGES:
            if route == "LOGIN":
                continue  # Already captured

            print(f"Capturing {description} ({route})...")
            try:
                page.goto(f"{base_url}/{route}", wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(wait_ms)

                # Scroll to top
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(500)

                filepath = os.path.join(SCREENSHOT_DIR, filename)
                page.screenshot(path=filepath, full_page=True)
                print(f"  Saved: {filepath}")
            except Exception as e:
                print(f"  ERROR capturing {description}: {e}")
                # Save whatever is visible
                try:
                    filepath = os.path.join(SCREENSHOT_DIR, filename)
                    page.screenshot(path=filepath, full_page=False)
                    print(f"  Saved (partial): {filepath}")
                except Exception:
                    print(f"  SKIP: Could not capture {description}")

        # 4) Capture settings sub-tabs
        settings_tabs = [
            ("Job Sources", "21a_settings_job_sources.png"),
            ("AI / LLM", "21b_settings_ai_llm.png"),
            ("Contacts", "21c_settings_contacts.png"),
            ("Validation", "21d_settings_validation.png"),
            ("Outreach", "21e_settings_outreach.png"),
            ("Business Rules", "21f_settings_business_rules.png"),
            ("Automation", "21g_settings_automation.png"),
        ]

        for tab_name, filename in settings_tabs:
            print(f"Capturing Settings > {tab_name}...")
            try:
                page.goto(f"{base_url}/dashboard/settings", wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(1500)

                # Click the tab
                tab_btn = page.locator(f'button:has-text("{tab_name}")').first
                if tab_btn.is_visible():
                    tab_btn.click()
                    page.wait_for_timeout(1500)

                page.evaluate("window.scrollTo(0, 0)")
                filepath = os.path.join(SCREENSHOT_DIR, filename)
                page.screenshot(path=filepath, full_page=True)
                print(f"  Saved: {filepath}")
            except Exception as e:
                print(f"  ERROR capturing Settings > {tab_name}: {e}")

        browser.close()

    print(f"\nAll screenshots saved to: {SCREENSHOT_DIR}")
    print(f"Total files: {len(os.listdir(SCREENSHOT_DIR))}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture SOP screenshots")
    parser.add_argument("--base-url", default="http://localhost:3000",
                        help="Base URL of the frontend (default: http://localhost:3000)")
    parser.add_argument("--email", default="superadmin@exzelon.com",
                        help="Login email")
    parser.add_argument("--password", default="SA@Admin#123",
                        help="Login password")
    args = parser.parse_args()

    capture_screenshots(args.base_url, args.email, args.password)
