import asyncio
import csv
import random
import pandas as pd
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import json

class IIMJobsScraper:
    def __init__(self):
        self.base_url = "https://www.iimjobs.com/search/hr-jobs"
        self.jobs_data = []
        
    async def random_delay(self, min_seconds=1, max_seconds=3):
        """Add random delay to mimic human behavior"""
        await asyncio.sleep(random.uniform(min_seconds, max_seconds))
    
    async def apply_stealth(self, page):
        """Apply stealth techniques to avoid detection"""
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false,
            });

            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });

            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });

            window.chrome = {
                runtime: {},
            };

            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    return [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
                    ];
                },
            });
        """)
    
    async def setup_browser(self, playwright):
        """Setup browser with stealth mode and anti-detection measures"""
        browser = await playwright.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-gpu',
                '--disable-infobars',
                '--window-size=1920,1080',
                '--start-maximized',
            ]
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='Asia/Kolkata',
            permissions=['geolocation'],
            geolocation={'latitude': 28.6139, 'longitude': 77.2090},
            java_script_enabled=True,
            has_touch=False,
            is_mobile=False,
        )
        
        await context.set_extra_http_headers({
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        })
        
        page = await context.new_page()
        await self.apply_stealth(page)
        
        return browser, page
    
    async def handle_captcha(self, page):
        """Wait for manual CAPTCHA solving if present"""
        try:
            captcha_selectors = [
                'iframe[src*="captcha"]',
                'iframe[src*="recaptcha"]',
                '.g-recaptcha',
                '#captcha',
                '[class*="captcha"]',
                '[id*="captcha"]',
            ]
            
            for selector in captcha_selectors:
                captcha = await page.query_selector(selector)
                if captcha:
                    print("\n" + "="*60)
                    print("⚠️  CAPTCHA DETECTED!")
                    print("="*60)
                    print("Please solve the CAPTCHA manually in the browser window.")
                    print("Waiting 30 seconds for you to solve it...")
                    print("="*60 + "\n")
                    await asyncio.sleep(30)
                    break
        except Exception as e:
            print(f"CAPTCHA check error: {e}")
    
    async def extract_job_details(self, page, job_element):
        """Extract detailed information from a job listing"""
        try:
            job_data = {
                'title': '',
                'company': '',
                'location': '',
                'experience': '',
                'salary': '',
                'posted_date': '',
                'job_type': '',
                'education': '',
                'industry': '',
                'functional_area': '',
                'role': '',
                'skills': '',
                'job_description': '',
                'url': '',
                'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # Get all text from the element for analysis
            all_text = (await job_element.inner_text()).strip()
            
            # Helper to check link
            tag_name = await job_element.evaluate("el => el.tagName")
            if tag_name == 'A':
                href = await job_element.get_attribute('href')
                if href and '/j/' in href:
                    job_data['url'] = href if href.startswith('http') else f"https://www.iimjobs.com{href}"

            # Skip if this is a "Featured Institute" or promotional element
            if 'Featured Institute' in all_text or 'IIT Delhi' in all_text and len(all_text) < 50:
                return None
            
            # Job Title - try multiple selectors
            title_selectors = [
                'h3', 
                '.job-title', 
                '[class*="title"]', 
                'h2 a', 
                'a.jobtitle',
                'a[class*="title"]',
                '.position',
                '[class*="position"]'
            ]
            
            for selector in title_selectors:
                title_elem = await job_element.query_selector(selector)
                if title_elem:
                    title_text = (await title_elem.inner_text()).strip()
                    # Skip if it's just promotional text
                    if title_text and 'Featured' not in title_text and 'IIT' not in title_text:
                        job_data['title'] = title_text
                        break
            
            # Company Name
            company_selectors = [
                '.company-name', 
                '[class*="company"]', 
                '.rec-name', 
                'a[href*="company"]', 
                '.companyname',
                '[class*="recruiter"]'
            ]
            
            for selector in company_selectors:
                company_elem = await job_element.query_selector(selector)
                if company_elem:
                    company_text = (await company_elem.inner_text()).strip()
                    if company_text and 'Featured' not in company_text:
                        job_data['company'] = company_text
                        break
            
            # Location
            location_selectors = [
                '.location', 
                '[class*="location"]', 
                '.loc', 
                '[class*="loc"]',
                'span[class*="location"]'
            ]
            
            for selector in location_selectors:
                location_elem = await job_element.query_selector(selector)
                if location_elem:
                    job_data['location'] = (await location_elem.inner_text()).strip()
                    break
            
            # Experience
            exp_selectors = [
                '.experience', 
                '[class*="exp"]', 
                '[class*="experience"]',
                'span[class*="exp"]'
            ]
            
            for selector in exp_selectors:
                exp_elem = await job_element.query_selector(selector)
                if exp_elem:
                    exp_text = (await exp_elem.inner_text()).strip()
                    # Look for patterns like "5-8 years" or "3+ years"
                    if 'year' in exp_text.lower() or '-' in exp_text:
                        job_data['experience'] = exp_text
                        break
            
            # Salary
            salary_selectors = [
                '.salary', 
                '[class*="salary"]', 
                '[class*="ctc"]',
                'span[class*="salary"]'
            ]
            
            for selector in salary_selectors:
                salary_elem = await job_element.query_selector(selector)
                if salary_elem:
                    salary_text = (await salary_elem.inner_text()).strip()
                    if 'lakh' in salary_text.lower() or 'lpa' in salary_text.lower():
                        job_data['salary'] = salary_text
                        break
            
            # Posted Date
            date_selectors = [
                '.posted', 
                '[class*="posted"]', 
                '[class*="date"]', 
                'time',
                'span[class*="date"]'
            ]
            
            for selector in date_selectors:
                date_elem = await job_element.query_selector(selector)
                if date_elem:
                    job_data['posted_date'] = (await date_elem.inner_text()).strip()
                    break
            
            # Job URL
            link_selectors = [
                'a[href*="job"]', 
                'a[href*="/j/"]', 
                'a.jobtitle',
                'a[class*="title"]'
            ]
            
            for selector in link_selectors:
                link_elem = await job_element.query_selector(selector)
                if link_elem:
                    href = await link_elem.get_attribute('href')
                    if href and 'job' in href.lower():
                        job_data['url'] = href if href.startswith('http') else f"https://www.iimjobs.com{href}"
                        break
            
            # Education
            if 'MBA' in all_text or 'Graduate' in all_text or 'Post Graduate' in all_text:
                edu_keywords = ['MBA', 'PGDM', 'Graduate', 'Post Graduate', 'B.Tech', 'M.Tech', 'Diploma']
                found_edu = [keyword for keyword in edu_keywords if keyword in all_text]
                if found_edu:
                    job_data['education'] = ', '.join(found_edu)
            
            # Skills
            skills_keywords = [
                'Recruitment', 'Talent Acquisition', 'HR Operations', 'Payroll', 
                'Employee Engagement', 'Performance Management', 'HRIS', 'Compensation',
                'Learning & Development', 'L&D', 'Training', 'HR Analytics', 'Sourcing',
                'Onboarding', 'Employee Relations', 'HR Policies'
            ]
            found_skills = [skill for skill in skills_keywords if skill.lower() in all_text.lower()]
            if found_skills:
                job_data['skills'] = ', '.join(found_skills)
            
            # Fallback: Parse from full text if selectors failed
            if not job_data['title'] and all_text:
                import re
                # Try to clean text mostly
                clean_text = all_text.replace('\n', ' ').strip()
                
                # Regex for Experience
                exp_match = re.search(r'(\d+\s*-\s*\d+\s*yrs)', clean_text)
                if exp_match:
                    job_data['experience'] = exp_match.group(1)
                
                # Deduce Title and Company (assuming "Company - Title ...")
                # Pattern: "Company - Title ... premium_icon" or just start
                # Usually text starts with "Company - Title"
                if ' - ' in clean_text:
                    parts = clean_text.split(' - ', 1)
                    if len(parts) >= 2:
                        job_data['company'] = parts[0].strip()
                        # Title is part[1] up to some keyword
                        rest = parts[1]
                        # Cut off at experience or keywords
                        cut_indices = []
                        if exp_match: cut_indices.append(rest.find(exp_match.group(1)))
                        if 'premium_icon' in rest: cut_indices.append(rest.find('premium_icon'))
                        
                        cut = min([i for i in cut_indices if i > 0], default=len(rest))
                        job_data['title'] = rest[:cut].strip()

                # Location: After experience "yrs . Location Posted"
                if job_data['experience']:
                    # find "yrs . "
                    loc_pattern = r'yrs\s*\.\s*(.*?)\s*Posted'
                    loc_match = re.search(loc_pattern, clean_text)
                    if loc_match:
                        job_data['location'] = loc_match.group(1).strip()
                
                # Posted Date
                post_match = re.search(r'Posted\s+(.*?)(?:\s+star|\s+grey|\s+Reviews|$)', clean_text)
                if post_match:
                    job_data['posted_date'] = post_match.group(1).strip()

            # Job Description (get more context)
            job_data['job_description'] = all_text[:500]  # First 500 chars
            
            return job_data
            
        except Exception as e:
            print(f"Error extracting job details: {e}")
            return None
    
    async def scrape_page(self, page, page_num=1):
        """Scrape all jobs from current page"""
        print(f"\n📄 Scraping page {page_num}...")
        
        # Construct URL with page parameter
        url = f"{self.base_url}?page={page_num}&loc=&posting=&category=&searchType=&method="
        print(f"🌐 URL: {url}")
        
        # Navigate to the page
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
        except Exception as e:
            print(f"❌ Error loading page: {e}")
            return False
        
        await self.random_delay(3, 5)
        
        # Check for CAPTCHA
        await self.handle_captcha(page)
        
        # Wait for job listings to load
        try:
            await page.wait_for_selector('.row, .job-list, [class*="job"], article, .card, .list', timeout=15000)
        except PlaywrightTimeout:
            print("⚠️  Timeout waiting for job listings.")
            return False
        
        await self.random_delay(1, 2)
        
        # Scroll to load dynamic content
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight/2)')
        await self.random_delay(0.5, 1)
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await self.random_delay(1, 2)
        
        # Find all job cards/listings
        job_selectors = [
            'a[href*="/j/"]',  # Direct job links
            '.job-list a',     # Links inside job-list
            'article',
            '.job-card',
            '.job-list-item',
            '.job-listing',
            '[class*="job-card"]',
            '[class*="jobCard"]',
            '[id*="job"]',
            '.card',
            '.list > div',
            '.row > div[class*="col"]',
            'li[id*="job"]',
            'div[id*="job"]',
            '.jobdetail',
            '[class*="jobdetail"]'
        ]
        
        job_elements = []
        for selector in job_selectors:
            elements = await page.query_selector_all(selector)
            if elements and len(elements) >= 2:  # At least 2 elements
                job_elements = elements
                print(f"✓ Found {len(job_elements)} elements using selector: {selector}")
                break
        
        if not job_elements:
            print("⚠️  No job listings found.")
            # Save debug info
            content = await page.content()
            with open(f'debug_page_{page_num}.html', 'w', encoding='utf-8') as f:
                f.write(content)
            await page.screenshot(path=f'debug_page_{page_num}.png', full_page=True)
            print(f"💾 Debug files saved: debug_page_{page_num}.html and debug_page_{page_num}.png")
            return False
        
        # Extract data from each job listing
        jobs_found = 0
        for idx, job_elem in enumerate(job_elements, 1):
            try:
                job_data = await self.extract_job_details(page, job_elem)
                if job_data and job_data['title']:  # Only add if we got a real title
                    # Check for duplicates
                    is_duplicate = False
                    for existing_job in self.jobs_data:
                        if (existing_job['title'] == job_data['title'] and 
                            existing_job['company'] == job_data['company']):
                            is_duplicate = True
                            break
                    
                    if not is_duplicate:
                        self.jobs_data.append(job_data)
                        jobs_found += 1
                        print(f"  ✓ Job {jobs_found}: {job_data['title'][:60]}...")
                        if job_data['company']:
                            print(f"      Company: {job_data['company']}")
                        if job_data['location']:
                            print(f"      Location: {job_data['location']}")
                
                await self.random_delay(0.2, 0.5)
            except Exception as e:
                print(f"  ✗ Error processing element {idx}: {e}")
                continue
        
        print(f"\n✅ Successfully extracted {jobs_found} unique jobs from page {page_num}")
        return jobs_found > 0
    
    async def save_to_csv(self, filename='iimjobs_hr_jobs.csv'):
        """Save scraped data to CSV file using Pandas for better organization"""
        if not self.jobs_data:
            print("⚠️  No data to save!")
            return None
        
        # Create DataFrame
        df = pd.DataFrame(self.jobs_data)
        
        # Define preferred column order for better readability
        preferred_order = [
            'title', 'company', 'location', 'experience', 'salary', 
            'posted_date', 'skills', 'education', 'url', 'scraped_at', 
            'job_description'
        ]
        
        # Reorder columns: preferred ones first, then any others extracted
        existing_cols = list(df.columns)
        final_cols = [c for c in preferred_order if c in existing_cols]
        final_cols += [c for c in existing_cols if c not in final_cols]
        
        df = df[final_cols]
        
        # Save to CSV using pandas (handles quoting and special characters robustly)
        # quotechar='"' and quoting=csv.QUOTE_ALL (1) ensures all fields are quoted
        df.to_csv(filename, index=False, encoding='utf-8-sig', quoting=csv.QUOTE_ALL)
        
        print(f"\n✅ Successfully saved {len(df)} jobs to {filename}")
        print("\n📊 DataFrame Preview:")
        print(df.head())
        print(f"\nℹ️  Columns: {', '.join(df.columns)}")
        
        return filename
    
    async def scrape(self, max_pages=10):
        """Main scraping function"""
        async with async_playwright() as playwright:
            browser = None
            try:
                browser, page = await self.setup_browser(playwright)
                
                print("="*60)
                print("🚀 IIMJobs HR Position Scraper")
                print("="*60)
                print(f"🌐 Base URL: {self.base_url}")
                print(f"📄 Max pages to scrape: {max_pages}")
                print("="*60 + "\n")
                
                # Scrape pages 1 through max_pages
                for page_num in range(1, max_pages + 1):
                    success = await self.scrape_page(page, page_num)
                    
                    if not success:
                        print(f"⚠️  No jobs found on page {page_num}. Stopping here.")
                        break
                    
                    print(f"📊 Total unique jobs collected: {len(self.jobs_data)}")
                    
                    # Small delay between pages
                    if page_num < max_pages:
                        await self.random_delay(2, 4)
                
                # Save results
                if self.jobs_data:
                    csv_path = await self.save_to_csv()
                    
                    print("\n" + "="*60)
                    print("🎉 SCRAPING COMPLETED!")
                    print("="*60)
                    print(f"📊 Total unique jobs scraped: {len(self.jobs_data)}")
                    print(f"📁 Data saved to: {csv_path}")
                    print("="*60)
                else:
                    print("\n❌ No jobs were scraped. Please check the debug files.")
                
            except KeyboardInterrupt:
                print("\n\n⚠️  Scraping interrupted by user.")
                if self.jobs_data:
                    await self.save_to_csv('iimjobs_hr_jobs_partial.csv')
                    print("💾 Partial data saved.")
                
            except Exception as e:
                print(f"\n❌ Error during scraping: {e}")
                import traceback
                traceback.print_exc()
                
            finally:
                if browser:
                    try:
                        print("\n🔄 Closing browser...")
                        await browser.close()
                        print("✅ Browser closed.")
                    except:
                        pass  # Ignore browser close errors


async def main():
    scraper = IIMJobsScraper()
    await scraper.scrape(max_pages=10)  # Adjust max_pages as needed

if __name__ == "__main__":
    print("\n" + "="*60)
    print("Starting IIMJobs Scraper...")
    print("="*60)
    asyncio.run(main())