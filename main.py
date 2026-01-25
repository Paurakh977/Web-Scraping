import time
import json
import re
import pandas as pd
import random
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

def scrape_indeed_stealth(job_search, location, pages_to_scrape=3):
    # --- 1. Setup Undetected Chrome (Bypasses Cloudflare) ---
    options = uc.ChromeOptions()
    # options.add_argument("--headless") # NEVER use headless with Indeed, it triggers immediate blocks
    
    # Initialize the stealth driver
    # Note: This might take a few seconds to start as it patches the browser
    print("Starting stealth browser...")
    driver = uc.Chrome(options=options)
    
    all_jobs = []
    
    try:
        for page in range(pages_to_scrape):
            start_param = page * 10
            url = f"https://www.indeed.com/jobs?q={job_search}&l={location}&start={start_param}"
            
            print(f"\n--- Navigating to Page {page + 1} ---")
            driver.get(url)
            
            # Random wait (Human behavior)
            time.sleep(random.uniform(4, 7))
            
            # --- Retry Loop for Captcha Handling ---
            # If we don't find data, we assume it's a Captcha and ask for help
            data_found = False
            retries = 0
            
            while not data_found and retries < 3:
                page_source = driver.page_source
                
                # Regex to find the JSON blob
                pattern = re.compile(r'window.mosaic.providerData\["mosaic-provider-jobcards"\]\s*=\s*({.*?});', re.DOTALL)
                match = pattern.search(page_source)
                
                if match:
                    # Data found successfully
                    json_data = json.loads(match.group(1))
                    results = json_data.get('metaData', {}).get('mosaicProviderJobCardsModel', {}).get('results', [])
                    
                    print(f"  -> Success! Found {len(results)} jobs.")
                    
                    for job in results:
                        # Extract Data
                        title = job.get('displayTitle', 'N/A')
                        company = job.get('company', 'N/A')
                        location_text = job.get('formattedLocation', 'N/A')
                        job_key = job.get('jobkey')
                        link = f"https://www.indeed.com/viewjob?jk={job_key}" if job_key else "N/A"
                        
                        # Date Posted
                        date_posted = job.get('formattedRelativeTime', 'N/A')
                        
                        # Summary (Snippet)
                        snippet_html = job.get('snippet', 'N/A')
                        snippet_clean = re.sub('<[^<]+?>', '', snippet_html) if isinstance(snippet_html, str) else "N/A"

                        # Salary
                        salary_info = job.get('extractedSalary', {})
                        if salary_info:
                            salary = salary_info.get('max', salary_info.get('display', 'N/A'))
                        else:
                            salary = "N/A"

                        all_jobs.append({
                            "Title": title,
                            "Company": company,
                            "Location": location_text,
                            "Date_Posted": date_posted,
                            "Salary": salary,
                            "Summary": snippet_clean,
                            "Link": link
                        })
                    
                    data_found = True # Exit the retry loop
                    
                else:
                    # --- CAPTCHA / BLOCK HANDLER ---
                    print(f"\n⚠️  WARNING: Could not find job data on Page {page + 1}.")
                    print("This usually means a CAPTCHA is on the screen.")
                    print("ACTION REQUIRED: Please verify you are human in the browser window.")
                    
                    # Wait for user to solve it
                    input(">>> Press ENTER here once the jobs are visible on the screen... <<<")
                    
                    # After user presses enter, we refresh the source variable (not the page)
                    print("Retrying extraction...")
                    retries += 1
            
            if not data_found:
                print(f"Skipping Page {page+1} after multiple failed attempts.")

    except Exception as e:
        print(f"Critical Error: {e}")
    finally:
        driver.quit()
        
    return all_jobs

# --- Execution ---
if __name__ == "__main__":
    search_query = "python developer"
    search_location = "Remote"
    
    # Try 3 pages
    data = scrape_indeed_stealth(search_query, search_location, pages_to_scrape=3)
    
    if data:
        df = pd.DataFrame(data)
        print(f"\nTotal Jobs Scraped: {len(df)}")
        df.to_csv("indeed_jobs_stealth.csv", index=False)
        print("Saved to indeed_jobs_stealth.csv")
    else:
        print("No data extracted.")