import asyncio
from playwright.async_api import async_playwright
import time

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        # Test Desktop
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        print("Testing Chat tab...")
        await page.goto("http://127.0.0.1:7860/")
        await page.wait_for_selector("#query_input")
        
        # Ask question
        await page.fill("#query_input", "Student list navigation")
        await page.click("button:has-text('Ask')")
        try:
            await page.wait_for_selector(".answer-box", timeout=30000)
            await page.wait_for_selector(".system-path-diagram", timeout=10000)
            print("System Path Diagram loaded!")
        except Exception as e:
            print("Chat answer or System path diagram error:", e)
        
        # Tabs test
        print("Testing FAQ Tab...")
        await page.click("button[data-tab='faq']")
        await asyncio.sleep(2)
        try:
            await page.wait_for_selector(".faq-item")
            print("FAQs loaded!")
        except Exception:
            print("FAQ load failed")

        print("Testing Dashboard Tab...")
        await page.click("button[data-tab='dashboard']")
        await asyncio.sleep(2)
        try:
            await page.wait_for_selector(".stat-card")
            print("Dashboard loaded!")
        except:
            print("Dashboard load failed")

        print("Testing Admin Tab...")
        await page.click("button[data-tab='admin']")
        await asyncio.sleep(2)
        try:
            await page.wait_for_selector(".admin-table")
            print("Admin Panel loaded!")
        except:
            print("Admin Panel load failed")

        # Test Mobile
        print("Testing Mobile Layout...")
        mobile_page = await browser.new_page(viewport={"width": 390, "height": 844})
        await mobile_page.goto("http://127.0.0.1:7860/")
        await mobile_page.wait_for_selector("#query_input")
        print("Mobile layout rendered.")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
