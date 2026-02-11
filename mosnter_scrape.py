import json
import time
import random
import pandas as pd
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
# List of 20 tech-related job titles to scrape
JOB_KEYWORDS = [
    "python developer",
    "java developer",
    "javascript developer",
    "react developer",
    "node.js developer",
    "data scientist",
    "data analyst",
    "devops engineer",
    "software engineer",
    "full stack developer",
    "backend developer",
    "frontend developer",
    "c# developer",
    "dotnet developer",
    "cloud engineer",
    "machine learning engineer",
    "qa automation engineer",
    "cyber security analyst",
    "system administrator",
    "product manager"
]

LOCATION = "Remote"
PAGES_TO_SCRAPE_PER_KEYWORD = 5  # 5 pages * 20 keywords = 100 pages total
OUTPUT_FILE = "monster_jobs_all.csv"

def run():
    print(f">>> Initializing Playwright Scraper for {len(JOB_KEYWORDS)} keywords x {PAGES_TO_SCRAPE_PER_KEYWORD} pages...")
    
    all_jobs_data = []

    with sync_playwright() as p:
        # Launch browser (headless=False is SAFER to avoid detection)
        browser = p.chromium.launch(
            headless=False, 
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        # Create a stealth context
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='America/New_York'
        )
        
        # Inject Stealth JavaScript
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = context.new_page()

        # --- KEYWORD LOOP ---
        for keyword in JOB_KEYWORDS:
            search_query = keyword.replace(" ", "+")
            print(f"\n\n=== STARTING SCRAPE FOR KEYWORD: '{keyword}' ===")

            # --- PAGINATION LOOP ---
            for current_page in range(1, PAGES_TO_SCRAPE_PER_KEYWORD + 1):
                print(f"\n--- SCRAPING PAGE {current_page} of {PAGES_TO_SCRAPE_PER_KEYWORD} (Keyword: {keyword}) ---")
                
                # Construct URL dynamically
                url = f"https://www.monster.com/jobs/search?q={search_query}&where={LOCATION}&page={current_page}&so=m.h.s"
                
                try:
                    print(f">>> Navigating to: {url}")
                    page.goto(url, timeout=60000)
                    
                    # Wait for network idle (handle redirects)
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except:
                        print(">>> Network busy, proceeding anyway...")

                    # Random sleep (mimic human reading)
                    time.sleep(random.uniform(3, 6))

                    # Scroll to bottom to trigger lazy loading
                    try:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        time.sleep(3)
                    except:
                        pass

                    page_jobs = []
                    
                    # --- STRATEGY 1: JSON Extraction ---
                    try:
                        raw_json = page.evaluate("""() => {
                            const script = document.getElementById('__NEXT_DATA__');
                            return script ? script.innerText : null;
                        }""")

                        if raw_json:
                            data = json.loads(raw_json)
                            queries = data.get('props', {}).get('pageProps', {}).get('dehydratedState', {}).get('queries', [])
                            
                            found_json = False
                            for query in queries:
                                state_data = query.get('state', {}).get('data', {})
                                if state_data and 'jobResults' in state_data:
                                    results = state_data.get('jobResults', [])
                                    for job in results:
                                        page_jobs.append({
                                            "Job ID": job.get('jobId'),
                                            "Title": job.get('jobTitle'),
                                            "Company": job.get('company', {}).get('name'),
                                            "Location": job.get('location'),
                                            "Date Posted": job.get('datePosted'),
                                            "Salary": job.get('salary', {}).get('salaryText') or "N/A",
                                            "Apply URL": job.get('jobPostingUrl'),
                                            "Source": "JSON",
                                            "Keyword": keyword # Track which keyword found this job
                                        })
                                    found_json = True
                                    break
                            if found_json:
                                print(f">>> Extracted {len(page_jobs)} jobs from JSON.")
                    except Exception:
                        pass

                    # --- STRATEGY 2: Visual Fallback (If JSON empty) ---
                    if not page_jobs:
                        print(">>> JSON empty. Switching to Visual Scraping...")
                        try:
                            # Increased timeout to 20s and added error debugging
                            page.wait_for_selector('div[data-testid="job-card-component"], article', timeout=20000)
                        except:
                            print(f"!!! No cards found on page {current_page}. Taking screenshot...")
                            page.screenshot(path=f"debug_error_{keyword.replace(' ', '_')}_{current_page}.png")
                            print(f"!!! Screenshot saved. Checking Page Title: {page.title()}")
                            
                            # Check if we hit a captcha or block
                            content = page.content().lower()
                            if "captcha" in content or "robot" in content or "denied" in content:
                                print("!!! ANTI-BOT DETECTION TRIGGERED.")
                            
                            break # Stop loop if no cards found

                        cards = page.locator('div[data-testid="job-card-component"]').all()
                        if not cards:
                            cards = page.locator('article').all()
                        
                        print(f">>> Found {len(cards)} visual cards.")

                        for card in cards:
                            try:
                                title_el = card.locator('[data-testid="jobTitle"]')
                                company_el = card.locator('[data-testid="company"]')
                                loc_el = card.locator('[data-testid="jobLocation"]')
                                
                                link = title_el.get_attribute('href')
                                if link and not link.startswith('http'):
                                    link = 'https:' + link

                                page_jobs.append({
                                    "Job ID": "N/A",
                                    "Title": title_el.inner_text().strip() if title_el.count() else "N/A",
                                    "Company": company_el.inner_text().strip() if company_el.count() else "N/A",
                                    "Location": loc_el.inner_text().strip() if loc_el.count() else "N/A",
                                    "Date Posted": "N/A",
                                    "Salary": "N/A",
                                    "Apply URL": link,
                                    "Source": "Visual",
                                    "Keyword": keyword
                                })
                            except:
                                continue

                    # Add page results to main list
                    if page_jobs:
                        all_jobs_data.extend(page_jobs)
                        print(f">>> Page {current_page} complete. Total jobs so far: {len(all_jobs_data)}")
                    else:
                        print("!!! No jobs found on this page. Moving to next keyword.")
                        break

                except Exception as e:
                    print(f"!!! Error on page {current_page} for '{keyword}': {e}")

            # Small pause between keywords to be polite
            print(f">>> Finished keyword '{keyword}'. Sleeping briefly...")
            time.sleep(5)

        # --- SAVE FINAL DATA ---
        print("\n>>> SAVING DATA...")
        if all_jobs_data:
            df = pd.DataFrame(all_jobs_data)
            # Remove duplicates based on Apply URL
            df.drop_duplicates(subset=['Apply URL'], keep='first', inplace=True)
            
            df.to_csv(OUTPUT_FILE, index=False)
            print(f">>> SUCCESS! Saved {len(df)} unique jobs to '{OUTPUT_FILE}'")
            print(df.head())
        else:
            print("!!! No data extracted.")
        
        browser.close()

if __name__ == "__main__":
    run()
