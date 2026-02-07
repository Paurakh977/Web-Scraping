import asyncio
import json
import re
import pandas as pd
import random
import time
from datetime import datetime
from playwright.async_api import async_playwright

async def scrape_indeed_rich_data(job_search, location, max_pages=15):
    all_jobs = []
    
    async with async_playwright() as p:
        # Launch browser (Headless=False is safer to avoid detection)
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

        # Inject Stealth (prevents simple webdriver detection)
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
                # Wait for the main feed container
                await page.wait_for_selector('#mosaic-provider-jobcards', timeout=15000)
            except:
                print("  -> Jobs didn't load. Possible Captcha or Network issue.")
                # Optional: await page.pause() # Uncomment to manually solve captcha
                break

            # --- 2. Random Human Pause (Essential) ---
            await page.wait_for_timeout(random.randint(2000, 4000))

            # --- 3. Extract RICH JSON ---
            content = await page.content()
            
            # This Regex grabs the specific JS variable containing the JSON data
            pattern = re.compile(r'window.mosaic.providerData\["mosaic-provider-jobcards"\]\s*=\s*({.*?});', re.DOTALL)
            match = pattern.search(content)
            
            if match:
                try:
                    json_data = json.loads(match.group(1))
                    results = json_data.get('metaData', {}).get('mosaicProviderJobCardsModel', {}).get('results', [])
                    print(f"  -> Found {len(results)} jobs in JSON.")
                    
                    for job in results:
                        try:
                            # --- A. IDS & LINKS ---
                            jk = job.get('jobkey')
                            link = f"https://www.indeed.com/viewjob?jk={jk}" if jk else "N/A"

                            # --- B. SALARY (Structured + Fallback) ---
                            # Try to get the clean numbers first
                            salary_obj = job.get('extractedSalary')
                            salary_text = "N/A"
                            salary_min = None
                            salary_max = None
                            
                            if salary_obj:
                                salary_min = salary_obj.get('min')
                                salary_max = salary_obj.get('max')
                                s_type = salary_obj.get('type', '')
                                salary_text = f"{salary_min} - {salary_max} ({s_type})"
                            
                            # Fallback to the snippet text if structured data is missing
                            if salary_text == "N/A":
                                salary_text = job.get('salarySnippet', {}).get('text', 'N/A')

                            # --- C. DATES (Timestamp Conversion) ---
                            pub_date_raw = job.get('pubDate') # timestamp in ms
                            if pub_date_raw:
                                pub_date = datetime.fromtimestamp(pub_date_raw / 1000).strftime('%Y-%m-%d')
                            else:
                                pub_date = "N/A"

                            # --- D. SKILLS / TECH STACK (The Hidden Gem) ---
                            # As analyzed, skills often appear in 'sortedMisMatchingEntityDisplayText' or 'sortedMatching...'
                            match_model = job.get('jobSeekerMatchSummaryModel', {})
                            
                            # Combine both lists to get full detected entities
                            skills_list = match_model.get('sortedMisMatchingEntityDisplayText', []) + \
                                          match_model.get('sortedMatchingEntityDisplayText', [])
                            
                            # Clean up duplicates and empty strings
                            skills_list = list(set([s for s in skills_list if s]))
                            skills_str = ", ".join(skills_list)

                            # --- E. JOB ATTRIBUTES ---
                            job_types = ", ".join(job.get('jobTypes', []))
                            
                            # Remote Logic: Check the model type OR the simple boolean
                            remote_model = job.get('remoteWorkModel', {})
                            is_remote = job.get('remoteLocation', False)
                            if remote_model.get('type') == 'REMOTE_ALWAYS':
                                is_remote = True

                            # --- F. DESCRIPTION SNIPPET ---
                            snippet_html = job.get('snippet', 'N/A')
                            snippet_clean = re.sub('<[^<]+?>', '', snippet_html).replace("\n", " ").strip()

                            # --- G. COMPANY METRICS ---
                            
                            all_jobs.append({
                                "Job_Key": jk,
                                "Title": job.get('displayTitle', job.get('title', 'N/A')),
                                "Company": job.get('company', 'N/A'),
                                "Rating": job.get('companyRating', 0),
                                "Review_Count": job.get('companyReviewCount', 0),
                                "Location": job.get('formattedLocation', 'N/A'),
                                "Is_Remote": is_remote,
                                "Salary_Text": salary_text,
                                "Salary_Min": salary_min, # Useful for numerical analysis later
                                "Salary_Max": salary_max, # Useful for numerical analysis later
                                "Job_Type": job_types,
                                "Date_Posted": pub_date,
                                "Date_Created": job.get('formattedRelativeTime', 'N/A'), # e.g. "3 days ago"
                                "Skills_Detected": skills_str,
                                "Summary": snippet_clean,
                                "Link": link
                            })
                        except Exception as e:
                            print(f"    Error parsing individual job: {e}")
                            continue

                except json.JSONDecodeError:
                    print("  -> Error decoding JSON data.")
            else:
                print("  -> ⚠️ No JSON data block found (Layout might have changed or Captcha triggered).")

            # --- 4. Pagination ---
            if current_page < max_pages:
                try:
                    # Handle "Sign in with Google" popups or other overlays
                    close_selectors = ['button[aria-label="close"]', '.icl-CloseButton', '[id^="google-one-tap-container"]']
                    for selector in close_selectors:
                        if await page.locator(selector).count() > 0:
                            if await page.locator(selector).is_visible():
                                await page.locator(selector).click()
                                await page.wait_for_timeout(500)

                    # Find Next Button
                    next_button = page.locator('[data-testid="pagination-page-next"]')
                    
                    if await next_button.count() > 0:
                        await next_button.scroll_into_view_if_needed()
                        await next_button.click()
                    else:
                        print("  -> 'Next' button not found. End of results.")
                        break
                except Exception as e:
                    print(f"  -> Error navigating to next page: {e}")
                    break
        
        await browser.close()
        return all_jobs

if __name__ == "__main__":
    # List of tech job titles and example locations (20+ pairs)
    JOB_LOCATION_PAIRS = [
        ("Product Manager", "Los Angeles, CA"),
        ("Technical Program Manager", "Chicago, IL"),
        ("UX Designer", "Boston, MA"),
        ("UI Designer", "Denver, CO"),
        ("Data Analyst", "Atlanta, GA"),
        ("Embedded Systems Engineer", "San Diego, CA"),
        ("Firmware Engineer", "Phoenix, AZ"),
        ("Hardware Engineer", "Philadelphia, PA"),
        ("Network Engineer", "Portland, OR"),
        ("Systems Architect", "Houston, TX"),
        ("Platform Engineer", "Raleigh, NC"),
        ("Game Developer", "San Jose, CA"),
        ("Graphics Programmer", "Oakland, CA"),
        ("Computer Vision Engineer", "Palo Alto, CA"),
        ("Robotics Engineer", "Cambridge, MA"),
        ("Research Engineer", "Bangalore, India"),
        ("Blockchain Developer", "London, UK"),
        ("Smart Contract Engineer", "Berlin, Germany"),
        ("Quantum Software Engineer", "Zurich, Switzerland"),
        ("Edge Computing Engineer", "Amsterdam, Netherlands"),
        ("IoT Engineer", "Tel Aviv, Israel"),
        ("AR/VR Developer", "Singapore"),
        ("GIS Developer", "Toronto, Canada"),
        ("Telemetry Engineer", "Dublin, Ireland"),
        ("Release Engineer", "Munich, Germany")
    ]

    all_results = []

    for idx, (title, location) in enumerate(JOB_LOCATION_PAIRS, start=1):
        print(f"\n=== [{idx}/{len(JOB_LOCATION_PAIRS)}] Scraping: '{title}' @ '{location}' (first page only) ===")
        try:
            results = asyncio.run(scrape_indeed_rich_data(title, location, max_pages=1))
        except Exception as e:
            print(f"  -> Error running scraper for '{title}' @ '{location}': {e}")
            results = []

        if results:
            # Annotate which search produced these rows
            for r in results:
                r["Search_Title"] = title
                r["Search_Location"] = location
            all_results.extend(results)
            print(f"  -> Collected {len(results)} jobs for '{title}'.")
        else:
            print(f"  -> No jobs collected for '{title}'.")

        # polite pause between queries
        time.sleep(random.randint(2, 5))

    # Save aggregated results
    if all_results:
        df = pd.DataFrame(all_results)
        print(f"\n✅ Total scraped jobs: {len(df)}")
        print(df[['Title', 'Company', 'Salary_Text', 'Date_Posted', 'Skills_Detected']].head())
        filename = f"indeed_jobs_bulk_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        df.to_csv(filename, index=False)
        print(f"Saved combined CSV to {filename}")
    else:
        print("No data extracted for any searches.")