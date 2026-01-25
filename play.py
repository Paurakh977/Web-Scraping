import asyncio
import json
import re
import pandas as pd
import random
from playwright.async_api import async_playwright

async def scrape_indeed_endurance(job_search, location, max_pages=15):
    all_jobs = []
    
    async with async_playwright() as p:
        # Launch browser (Headless=False is safer)
        browser = await p.chromium.launch(
            headless=False, 
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
        )
        
        # Setup Context
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        
        page = await context.new_page()

        # Inject Stealth (Hide Robot Status)
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        # Initial Navigation
        url = f"https://www.indeed.com/jobs?q={job_search}&l={location}"
        print(f"Navigating to: {url}")
        
        try:
            await page.goto(url, timeout=60000)
        except:
            print("Page load timeout - reloading...")
            await page.reload()

        for current_page in range(1, max_pages + 1):
            print(f"\n--- Processing Page {current_page} of {max_pages} ---")
            
            # --- 1. Wait for Jobs to Load ---
            try:
                # Wait up to 15 seconds for the job cards
                await page.wait_for_selector('#mosaic-provider-jobcards', timeout=15000)
            except:
                print("  -> Jobs didn't load. Possible Captcha or Network issue.")
                # Pause here to let you fix it manually if needed
                await page.pause()

            # --- 2. Random Human Pause (Vital for long runs) ---
            # Wait 3 to 6 seconds between pages
            await page.wait_for_timeout(random.randint(3000, 6000))

            # --- 3. Extract JSON ---
            content = await page.content()
            pattern = re.compile(r'window.mosaic.providerData\["mosaic-provider-jobcards"\]\s*=\s*({.*?});', re.DOTALL)
            match = pattern.search(content)
            
            if match:
                json_data = json.loads(match.group(1))
                results = json_data.get('metaData', {}).get('mosaicProviderJobCardsModel', {}).get('results', [])
                print(f"  -> Found {len(results)} jobs.")
                
                for job in results:
                    jk = job.get('jobkey')
                    all_jobs.append({
                        "Title": job.get('displayTitle', 'N/A'),
                        "Company": job.get('company', 'N/A'),
                        "Location": job.get('formattedLocation', 'N/A'),
                        "Date": job.get('formattedRelativeTime', 'N/A'),
                        "Link": f"https://www.indeed.com/viewjob?jk={jk}" if jk else "N/A"
                    })
            else:
                print("  -> ⚠️ No data found (Possible Captcha).")

            # --- 4. Pagination (Click Next) ---
            if current_page < max_pages:
                try:
                    # A. Kill Popups (Indeed throws these after page 3)
                    # We check for multiple types of close buttons
                    close_selectors = [
                        'button[aria-label="close"]', 
                        '.icl-CloseButton', 
                        '[id^=" google-one-tap-container"]' # Sometimes Google login
                    ]
                    for selector in close_selectors:
                        if await page.locator(selector).count() > 0:
                            if await page.locator(selector).is_visible():
                                print("  -> Closing popup...")
                                await page.locator(selector).click()
                                await page.wait_for_timeout(1000)

                    # B. Click Next
                    next_button = page.locator('[data-testid="pagination-page-next"]')
                    
                    if await next_button.count() > 0:
                        await next_button.scroll_into_view_if_needed()
                        await next_button.click()
                    else:
                        print("  -> 'Next' button gone. End of results.")
                        break
                        
                except Exception as e:
                    print(f"  -> Error clicking next: {e}")
                    break
        
        await browser.close()
        return all_jobs

if __name__ == "__main__":
    # --- CHANGE THIS NUMBER TO SCRAPE MORE ---
    PAGES_TO_SCRAPE = 10 
    
    data = asyncio.run(scrape_indeed_endurance("python developer", "Remote", max_pages=PAGES_TO_SCRAPE))
    
    if data:
        df = pd.DataFrame(data)
        print(f"\n✅ Final Results: Scraped {len(df)} jobs.")
        df.to_csv("indeed_jobs_large.csv", index=False)
        print("Saved to indeed_jobs_large.csv")