import asyncio
import json
import re
import pandas as pd
import random
from playwright.async_api import async_playwright

async def scrape_indeed_rich_data(job_search, location, max_pages=15):
    all_jobs = []
    
    async with async_playwright() as p:
        # Launch browser (Headless=False is safer)
        browser = await p.chromium.launch(
            headless=False, 
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
        )
        
        # Setup Context with High-Res Viewport
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        
        page = await context.new_page()

        # Inject Stealth
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
                await page.wait_for_selector('#mosaic-provider-jobcards', timeout=15000)
            except:
                print("  -> Jobs didn't load. Possible Captcha or Network issue.")
                await page.pause()

            # --- 2. Random Human Pause ---
            await page.wait_for_timeout(random.randint(3000, 5000))

            # --- 3. Extract RICH JSON ---
            content = await page.content()
            pattern = re.compile(r'window.mosaic.providerData\["mosaic-provider-jobcards"\]\s*=\s*({.*?});', re.DOTALL)
            match = pattern.search(content)
            
            if match:
                json_data = json.loads(match.group(1))
                results = json_data.get('metaData', {}).get('mosaicProviderJobCardsModel', {}).get('results', [])
                print(f"  -> Found {len(results)} jobs.")
                
                for job in results:
                    # --- DETAILED EXTRACTION START ---
                    
                    # 1. Job Key & Link
                    jk = job.get('jobkey')
                    link = f"https://www.indeed.com/viewjob?jk={jk}" if jk else "N/A"

                    # 2. Salary (Handle nested structure)
                    # Indeed stores salary in 'extractedSalary' -> 'display' OR 'max'/'min'
                    salary_obj = job.get('extractedSalary')
                    if salary_obj:
                        salary = salary_obj.get('display')
                        if not salary and salary_obj.get('max'):
                            salary = f"{salary_obj.get('min')} - {salary_obj.get('max')} {salary_obj.get('type', '')}"
                    else:
                        salary = "N/A"

                    # 3. Job Type (Full-time, Contract, etc)
                    # Stored as a list of strings
                    job_types_list = job.get('jobTypes', [])
                    job_type = ", ".join(job_types_list) if job_types_list else "N/A"

                    # 4. Snippet / Summary (Clean HTML tags)
                    snippet_html = job.get('snippet', 'N/A')
                    snippet_clean = re.sub('<[^<]+?>', '', snippet_html) if isinstance(snippet_html, str) else "N/A"
                    # Remove newlines for cleaner CSV
                    snippet_clean = snippet_clean.replace("\n", " ")

                    # 5. Company Rating & Reviews
                    rating = job.get('companyRating', 'N/A')
                    reviews = job.get('companyReviewCount', 0)

                    # 6. Attributes (Remote, Urgent, etc)
                    # Sometimes stored in 'remoteLocation' boolean
                    is_remote = job.get('remoteLocation', False)
                    # "Urgent Hiring" flag
                    is_urgent = job.get('urgent', False)

                    all_jobs.append({
                        "Title": job.get('displayTitle', 'N/A'),
                        "Company": job.get('company', 'N/A'),
                        "Location": job.get('formattedLocation', 'N/A'),
                        "Salary": salary,
                        "Job_Type": job_type,
                        "Rating": rating,
                        "Reviews": reviews,
                        "Is_Remote": is_remote,
                        "Urgent_Hiring": is_urgent,
                        "Date_Posted": job.get('formattedRelativeTime', 'N/A'),
                        "Summary": snippet_clean,
                        "Link": link
                    })
                    # --- DETAILED EXTRACTION END ---

            else:
                print("  -> ⚠️ No data found (Possible Captcha).")

            # --- 4. Pagination ---
            if current_page < max_pages:
                try:
                    # Kill Popups
                    close_selectors = ['button[aria-label="close"]', '.icl-CloseButton', '[id^=" google-one-tap-container"]']
                    for selector in close_selectors:
                        if await page.locator(selector).count() > 0:
                            if await page.locator(selector).is_visible():
                                await page.locator(selector).click()
                                await page.wait_for_timeout(500)

                    # Click Next
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
    # Scrape 10 Pages to test
    data = asyncio.run(scrape_indeed_rich_data("python developer", "Remote", max_pages=10))
    
    if data:
        df = pd.DataFrame(data)
        
        # Reorder columns for better readability
        cols = ["Title", "Company", "Salary", "Location", "Date_Posted", "Job_Type", "Rating", "Summary", "Link"]
        # Only select columns that exist (in case I missed one in the list above)
        df = df[cols] if set(cols).issubset(df.columns) else df
        
        print(f"\n✅ Final Results: Scraped {len(df)} jobs.")
        print(df.head())
        
        df.to_csv("indeed_jobs_extended.csv", index=False)
        print("Saved to indeed_jobs_extended.csv")