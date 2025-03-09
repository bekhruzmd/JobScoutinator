import time
import random
import pandas as pd
import gspread
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from google.oauth2.service_account import Credentials
from datetime import datetime
import logging
import argparse
import re

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 🔧 Configure Headless Selenium WebDriver for macOS
def setup_driver():
    options = Options()
    options.add_argument("--headless")  
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        return driver
    except Exception as e:
        logger.error(f"Failed to set up WebDriver: {e}")
        raise

# 🏗️ Function to Get Job Data from Indeed
def scrape_indeed(driver, job_title, location, filters=None):
    logger.info(f"Scraping Indeed for {job_title} in {location}")
    
    # Build URL with filters
    url = f"https://www.indeed.com/jobs?q={job_title.replace(' ', '+')}"
    
    # Add location
    if location:
        url += f"&l={location.replace(' ', '+')}"
    
    # Add filters
    if filters:
        if filters.get('date_posted'):
            # Convert date filter to Indeed format (1 = last 24 hours, 3 = last 3 days, 7 = last 7 days, etc.)
            date_map = {'24h': '1', '3d': '3', '7d': '7', '14d': '14', '30d': '30'}
            date_val = date_map.get(filters['date_posted'], '')
            if date_val:
                url += f"&fromage={date_val}"
        
        if filters.get('job_type'):
            # Convert job type filter to Indeed format
            type_map = {'full_time': 'fulltime', 'part_time': 'parttime', 'contract': 'contract', 'temporary': 'temporary', 'internship': 'internship'}
            type_val = type_map.get(filters['job_type'], '')
            if type_val:
                url += f"&jt={type_val}"
        
        if filters.get('experience_level'):
            # Indeed uses 'explvl' parameter for experience level
            exp_map = {'entry': 'entry_level', 'mid': 'mid_level', 'senior': 'senior_level'}
            exp_val = exp_map.get(filters['experience_level'], '')
            if exp_val:
                url += f"&explvl={exp_val}"
        
        if filters.get('salary_min'):
            url += f"&salary={filters['salary_min']}"
        
        if filters.get('remote'):
            url += "&remotejob=1"
    
    try:
        driver.get(url)
        time.sleep(random.uniform(3, 6))  # Mimic human behavior
        
        job_list = []
        
        # Try different selectors as Indeed often changes their DOM structure
        possible_job_selectors = [
            "job_seen_beacon",
            "jobsearch-ResultsList",
            "tapItem",
            "job_seen_beacon"
        ]
        
        jobs = []
        for selector in possible_job_selectors:
            jobs = driver.find_elements(By.CLASS_NAME, selector)
            if jobs:
                logger.info(f"Found {len(jobs)} jobs on Indeed using selector: {selector}")
                break
        
        if not jobs:
            # Try a more generic approach
            jobs = driver.find_elements(By.CSS_SELECTOR, "div[data-testid='jobListing']")
            if jobs:
                logger.info(f"Found {len(jobs)} jobs on Indeed using generic selector")
            else:
                logger.warning("No jobs found on Indeed. The page structure might have changed.")
        
        for job in jobs[:20]:  # Limit to first 20 jobs for efficiency
            try:
                # Use multiple possible selectors for each element
                title = None
                for selector in ["jobTitle", "title", "jobName"]:
                    elements = job.find_elements(By.CLASS_NAME, selector)
                    if elements:
                        title = elements[0].text
                        break
                
                company = None
                for selector in ["companyName", "company", "companyInfo"]:
                    elements = job.find_elements(By.CLASS_NAME, selector)
                    if elements:
                        company = elements[0].text
                        break
                
                salary = "N/A"
                for selector in ["salary-snippet-container", "salaryOnly", "metadata salary"]:
                    elements = job.find_elements(By.CLASS_NAME, selector.replace(" ", "."))
                    if elements:
                        salary = elements[0].text
                        break
                
                link = None
                elements = job.find_elements(By.TAG_NAME, "a")
                if elements:
                    for element in elements:
                        href = element.get_attribute("href")
                        if href and "job" in href:
                            link = href
                            break
                
                posted_date = "N/A"
                for selector in ["date", "jobAge", "jobAgeDays"]:
                    elements = job.find_elements(By.CLASS_NAME, selector)
                    if elements:
                        posted_date = elements[0].text
                        break
                
                summary = "N/A"
                for selector in ["job-snippet", "jobDescription", "summary"]:
                    elements = job.find_elements(By.CLASS_NAME, selector)
                    if elements:
                        summary = elements[0].text
                        break
                
                if title and company:
                    job_list.append(["Indeed", title, company, salary, link or "N/A", posted_date, summary])
            except Exception as e:
                logger.warning(f"Error parsing Indeed job: {e}")
                continue
        
        logger.info(f"Successfully scraped {len(job_list)} jobs from Indeed")
        return job_list
    
    except Exception as e:
        logger.error(f"Error scraping Indeed: {e}")
        return []

# 🏗️ Function to Get Job Data from Glassdoor
def scrape_glassdoor(driver, job_title, location, filters=None):
    logger.info(f"Scraping Glassdoor for {job_title} in {location}")
    
    # Build URL with basic parameters
    location_formatted = location.replace(' ', '-').lower() if location else "united-states"
    job_title_formatted = job_title.replace(' ', '-').lower()
    
    # Base URL structure
    url = f"https://www.glassdoor.com/Job/{location_formatted}-{job_title_formatted}-jobs-SRCH_IL.0,{len(location_formatted)}_IC1132348_KO{len(location_formatted)+1},{len(location_formatted)+1+len(job_title_formatted)}.htm"
    
    try:
        driver.get(url)
        time.sleep(random.uniform(4, 7))  # Glassdoor can be slower to load
        
        # Handle Glassdoor sign-in popup if it appears
        try:
            close_buttons = driver.find_elements(By.CSS_SELECTOR, "span.SVGInline.modal_closeIcon")
            if close_buttons:
                close_buttons[0].click()
                time.sleep(1)
        except Exception as e:
            logger.warning(f"Could not close Glassdoor popup: {e}")
        
        # Apply filters
        if filters:
            try:
                # Click "More" button to show filters
                more_button = driver.find_elements(By.CSS_SELECTOR, "button[data-test='filters-more']")
                if more_button:
                    more_button[0].click()
                    time.sleep(1)
                
                # Date posted filter
                if filters.get('date_posted'):
                    date_map = {'24h': '1d', '3d': '3d', '7d': '7d', '14d': '14d', '30d': '30d'}
                    date_val = date_map.get(filters['date_posted'], '')
                    if date_val:
                        date_buttons = driver.find_elements(By.CSS_SELECTOR, f"[data-test='DATEPOSTED_{date_val}']")
                        if date_buttons:
                            date_buttons[0].click()
                            time.sleep(1)
                
                # Job type filter
                if filters.get('job_type'):
                    type_map = {'full_time': 'fulltime', 'part_time': 'parttime', 'contract': 'contract', 'temporary': 'temporary', 'internship': 'internship'}
                    type_val = type_map.get(filters['job_type'], '')
                    if type_val:
                        type_buttons = driver.find_elements(By.CSS_SELECTOR, f"[data-test='JOBTYPE_{type_val.upper()}']")
                        if type_buttons:
                            type_buttons[0].click()
                            time.sleep(1)
                
                # Experience level filter
                if filters.get('experience_level'):
                    exp_map = {'entry': 'entrylevel', 'mid': 'midlevel', 'senior': 'seniorlevel'}
                    exp_val = exp_map.get(filters['experience_level'], '')
                    if exp_val:
                        exp_buttons = driver.find_elements(By.CSS_SELECTOR, f"[data-test='EXPERIENCE_{exp_val.upper()}']")
                        if exp_buttons:
                            exp_buttons[0].click()
                            time.sleep(1)
                
                # Apply filters button
                apply_buttons = driver.find_elements(By.CSS_SELECTOR, "[data-test='apply-filters']")
                if apply_buttons:
                    apply_buttons[0].click()
                    time.sleep(2)
            
            except Exception as e:
                logger.warning(f"Error applying Glassdoor filters: {e}")
        
        job_list = []
        
        # Try different possible job listing selectors
        possible_job_selectors = [
            "react-job-listing",
            "jobCard",
            "JobCard_jobCard__JGRMQ"
        ]
        
        jobs = []
        for selector in possible_job_selectors:
            jobs = driver.find_elements(By.CLASS_NAME, selector)
            if jobs:
                logger.info(f"Found {len(jobs)} jobs on Glassdoor using selector: {selector}")
                break
        
        if not jobs:
            # Try a generic approach
            jobs = driver.find_elements(By.CSS_SELECTOR, "li[data-id]")
            if jobs:
                logger.info(f"Found {len(jobs)} jobs on Glassdoor using generic selector")
            else:
                logger.warning("No jobs found on Glassdoor. The page structure might have changed.")
        
        for job in jobs[:20]:  # Limit to first 20 jobs for efficiency
            try:
                # Try multiple selectors for each element
                title = None
                for selector in ["jobLink", "job-title", "jobTitle"]:
                    elements = job.find_elements(By.CLASS_NAME, selector)
                    if elements:
                        title = elements[0].text
                        break
                if not title:
                    elements = job.find_elements(By.CSS_SELECTOR, "a[data-test='job-link']")
                    if elements:
                        title = elements[0].text
                
                company = None
                for selector in ["d-flex", "employer-name", "companyName"]:
                    elements = job.find_elements(By.CLASS_NAME, selector)
                    if elements:
                        company = elements[0].text
                        break
                if not company:
                    elements = job.find_elements(By.CSS_SELECTOR, "[data-test='employer-name']")
                    if elements:
                        company = elements[0].text
                
                salary = "N/A"
                for selector in ["css-1hbqxax", "salary-estimate", "salaryEstimate"]:
                    elements = job.find_elements(By.CLASS_NAME, selector)
                    if elements:
                        salary = elements[0].text
                        break
                if salary == "N/A":
                    elements = job.find_elements(By.CSS_SELECTOR, "[data-test='detailSalary']")
                    if elements:
                        salary = elements[0].text
                
                link = None
                elements = job.find_elements(By.TAG_NAME, "a")
                if elements:
                    for element in elements:
                        href = element.get_attribute("href")
                        if href and "/job-listing/" in href:
                            link = href
                            break
                
                # Glassdoor doesn't always show post date in the listing
                posted_date = "N/A"
                
                # Get summary if available
                summary = "N/A"
                for selector in ["jobDescriptionContent", "description", "jobDesc"]:
                    elements = job.find_elements(By.CLASS_NAME, selector)
                    if elements:
                        summary = elements[0].text[:200] + "..." if len(elements[0].text) > 200 else elements[0].text
                        break
                
                if title and company:
                    job_list.append(["Glassdoor", title, company, salary, link or "N/A", posted_date, summary])
            
            except Exception as e:
                logger.warning(f"Error parsing Glassdoor job: {e}")
                continue
        
        logger.info(f"Successfully scraped {len(job_list)} jobs from Glassdoor")
        return job_list
    
    except Exception as e:
        logger.error(f"Error scraping Glassdoor: {e}")
        return []

# 🏗️ Function to Get Job Data from LinkedIn
def scrape_linkedin(driver, job_title, location, filters=None):
    logger.info(f"Scraping LinkedIn for {job_title} in {location}")
    
    # Build URL with filters
    url = f"https://www.linkedin.com/jobs/search/?keywords={job_title.replace(' ', '%20')}"
    
    # Add location
    if location:
        url += f"&location={location.replace(' ', '%20')}"
    
    # Add filters
    if filters:
        if filters.get('date_posted'):
            # Convert date filter to LinkedIn format (r86400 = last 24 hours, r259200 = last 3 days, etc.)
            date_map = {'24h': 'r86400', '3d': 'r259200', '7d': 'r604800', '14d': 'r1209600', '30d': 'r2592000'}
            date_val = date_map.get(filters['date_posted'], '')
            if date_val:
                url += f"&f_TPR={date_val}"
        
        if filters.get('job_type'):
            # Convert job type filter to LinkedIn format
            type_map = {'full_time': 'F', 'part_time': 'P', 'contract': 'C', 'temporary': 'T', 'internship': 'I'}
            type_val = type_map.get(filters['job_type'], '')
            if type_val:
                url += f"&f_JT={type_val}"
        
        if filters.get('experience_level'):
            # LinkedIn uses numeric codes for experience levels
            exp_map = {'entry': '1', 'mid': '2,3', 'senior': '4,5'}
            exp_val = exp_map.get(filters['experience_level'], '')
            if exp_val:
                url += f"&f_E={exp_val}"
        
        if filters.get('remote'):
            url += "&f_WT=2"
    
    try:
        driver.get(url)
        time.sleep(random.uniform(3, 6))
        
        job_list = []
        
        # Try different selectors to find job listings
        possible_job_selectors = [
            "base-search-card__info",
            "job-search-card",
            "jobs-search-results__list-item"
        ]
        
        jobs = []
        for selector in possible_job_selectors:
            jobs = driver.find_elements(By.CLASS_NAME, selector)
            if jobs:
                logger.info(f"Found {len(jobs)} jobs on LinkedIn using selector: {selector}")
                break
        
        if not jobs:
            # Try a generic approach
            jobs = driver.find_elements(By.CSS_SELECTOR, "li.jobs-search-results__list-item")
            if jobs:
                logger.info(f"Found {len(jobs)} jobs on LinkedIn using generic selector")
            else:
                logger.warning("No jobs found on LinkedIn. The page structure might have changed.")
        
        for job in jobs[:20]:  # Limit to first 20 jobs for efficiency
            try:
                # Try multiple possible selectors for each element
                title = None
                for selector in ["base-search-card__title", "job-card-list__title", "job-title"]:
                    elements = job.find_elements(By.CLASS_NAME, selector)
                    if elements:
                        title = elements[0].text
                        break
                
                company = None
                for selector in ["base-search-card__subtitle", "job-card-container__company-name", "job-card-container__primary-description"]:
                    elements = job.find_elements(By.CLASS_NAME, selector)
                    if elements:
                        company = elements[0].text
                        break
                
                # LinkedIn doesn't always show salary in the listings
                salary = "N/A"
                for selector in ["job-search-card__salary-info", "salary-badge"]:
                    elements = job.find_elements(By.CLASS_NAME, selector)
                    if elements:
                        salary = elements[0].text
                        break
                
                link = None
                elements = job.find_elements(By.TAG_NAME, "a")
                if elements:
                    for element in elements:
                        href = element.get_attribute("href")
                        if href and "/jobs/view/" in href:
                            link = href
                            break
                
                posted_date = "N/A"
                elements = job.find_elements(By.TAG_NAME, "time")
                if elements:
                    posted_date = elements[0].text
                    # Try to get datetime attribute if available
                    datetime_attr = elements[0].get_attribute("datetime")
                    if datetime_attr:
                        posted_date = datetime_attr
                
                # LinkedIn doesn't show job summary in the listings
                summary = "N/A"
                for selector in ["job-search-card__location", "location"]:
                    elements = job.find_elements(By.CLASS_NAME, selector)
                    if elements:
                        summary = f"Location: {elements[0].text}"
                        break
                
                if title and company:
                    job_list.append(["LinkedIn", title, company, salary, link or "N/A", posted_date, summary])
            
            except Exception as e:
                logger.warning(f"Error parsing LinkedIn job: {e}")
                continue
        
        logger.info(f"Successfully scraped {len(job_list)} jobs from LinkedIn")
        return job_list
    
    except Exception as e:
        logger.error(f"Error scraping LinkedIn: {e}")
        return []

# 🏗️ Function to Get Job Data from ZipRecruiter
def scrape_ziprecruiter(driver, job_title, location, filters=None):
    logger.info(f"Scraping ZipRecruiter for {job_title} in {location}")
    
    # Build URL with filters
    url = f"https://www.ziprecruiter.com/jobs-search?search={job_title.replace(' ', '+')}"
    
    # Add location
    if location:
        url += f"&location={location.replace(' ', '+')}"
    
    # Add filters
    if filters:
        if filters.get('date_posted'):
            # Convert date filter to ZipRecruiter format (1 = last 24 hours, 3 = last 3 days, etc.)
            date_map = {'24h': '1', '3d': '3', '7d': '7', '14d': '14', '30d': '30'}
            date_val = date_map.get(filters['date_posted'], '')
            if date_val:
                url += f"&days={date_val}"
        
        if filters.get('job_type'):
            # Convert job type filter to ZipRecruiter format
            type_map = {'full_time': 'full_time', 'part_time': 'part_time', 'contract': 'contract', 'temporary': 'temporary', 'internship': 'internship'}
            type_val = type_map.get(filters['job_type'], '')
            if type_val:
                url += f"&employment_type={type_val}"
        
        if filters.get('remote'):
            url += "&remote=true"
    
    try:
        driver.get(url)
        time.sleep(random.uniform(3, 6))
        
        job_list = []
        
        # Try different selectors to find job listings
        possible_job_selectors = [
            "job_result",
            "job_content",
            "jobList-item"
        ]
        
        jobs = []
        for selector in possible_job_selectors:
            jobs = driver.find_elements(By.CLASS_NAME, selector)
            if jobs:
                logger.info(f"Found {len(jobs)} jobs on ZipRecruiter using selector: {selector}")
                break
        
        if not jobs:
            # Try a generic approach
            jobs = driver.find_elements(By.CSS_SELECTOR, "article[data-job-id]")
            if jobs:
                logger.info(f"Found {len(jobs)} jobs on ZipRecruiter using generic selector")
            else:
                logger.warning("No jobs found on ZipRecruiter. The page structure might have changed.")
        
        for job in jobs[:20]:  # Limit to first 20 jobs for efficiency
            try:
                # Try multiple possible selectors for each element
                title = None
                for selector in ["job_title", "title", "jobTitle"]:
                    elements = job.find_elements(By.CLASS_NAME, selector)
                    if elements:
                        title = elements[0].text
                        break
                
                company = None
                for selector in ["hiring_company", "company", "companyName"]:
                    elements = job.find_elements(By.CLASS_NAME, selector)
                    if elements:
                        company = elements[0].text
                        break
                
                salary = "N/A"
                for selector in ["salary_estimate", "salary", "jobSalary"]:
                    elements = job.find_elements(By.CLASS_NAME, selector)
                    if elements:
                        salary = elements[0].text
                        break
                
                link = None
                elements = job.find_elements(By.TAG_NAME, "a")
                if elements:
                    for element in elements:
                        href = element.get_attribute("href")
                        if href and "/jobs/" in href:
                            link = href
                            break
                
                posted_date = "N/A"
                for selector in ["job_posted", "posted", "datePosted"]:
                    elements = job.find_elements(By.CLASS_NAME, selector)
                    if elements:
                        posted_date = elements[0].text
                        break
                
                summary = "N/A"
                for selector in ["job_snippet", "snippet", "jobSnippet"]:
                    elements = job.find_elements(By.CLASS_NAME, selector)
                    if elements:
                        summary = elements[0].text
                        break
                
                if title and company:
                    job_list.append(["ZipRecruiter", title, company, salary, link or "N/A", posted_date, summary])
            
            except Exception as e:
                logger.warning(f"Error parsing ZipRecruiter job: {e}")
                continue
        
        logger.info(f"Successfully scraped {len(job_list)} jobs from ZipRecruiter")
        return job_list
    
    except Exception as e:
        logger.error(f"Error scraping ZipRecruiter: {e}")
        return []

# 📌 Save Data to Google Sheets
def save_to_google_sheets(data, filters=None):
    try:
        SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
        client = gspread.authorize(creds)

        spreadsheet = client.open("Job Listings")
        today_str = datetime.today().strftime("%Y-%m-%d")
        
        # Add filter info to worksheet name if available
        worksheet_name = today_str
        if filters:
            filter_info = []
            if filters.get('job_title'):
                filter_info.append(filters['job_title'])
            if filters.get('location'):
                filter_info.append(filters['location'])
            if filter_info:
                worksheet_name += f" - {' '.join(filter_info)}"

        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
            # Clear existing data
            worksheet.clear()
        except:
            worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows="1000", cols="10")

        # Add headers with filter information
        headers = ["Source", "Job Title", "Company", "Salary", "Job Link", "Date Posted", "Summary"]
        worksheet.append_row(headers)
        
        # Add filter information as a separate row
        if filters:
            filter_row = ["Filters:"]
            filter_details = []
            for k, v in filters.items():
                if v:
                    filter_details.append(f"{k.replace('_', ' ').title()}: {v}")
            filter_row.append(", ".join(filter_details))
            worksheet.append_row(filter_row)
            worksheet.append_row([])  # Empty row for spacing
        
        # Add job data
        for job in data:
            worksheet.append_row(job)

        logger.info("✅ Job data uploaded to Google Sheets!")
        return True
    
    except Exception as e:
        logger.error(f"Error saving to Google Sheets: {e}")
        return False

# Function to parse salary ranges
def parse_salary(salary_str):
    if not salary_str or salary_str == "N/A":
        return None
    
    # Extract numbers from the string
    numbers = re.findall(r'\d[\d,]*(?:\.\d+)?', salary_str)
    if not numbers:
        return None
    
    # Convert to float
    try:
        numbers = [float(n.replace(',', '')) for n in numbers]
        # If we have two numbers, it's likely a range
        if len(numbers) >= 2:
            return sum(numbers[:2]) / 2  # Use average of min and max
        elif len(numbers) == 1:
            return numbers[0]
    except:
        pass
    
    return None

# 🔍 Function to filter jobs based on criteria
def filter_jobs(jobs, criteria):
    if not criteria:
        return jobs
    
    filtered_jobs = []
    for job in jobs:
        source, title, company, salary, link, posted_date, summary = job
        
        # Filter by keywords in title
        if criteria.get('keywords') and all(keyword.lower() not in title.lower() for keyword in criteria['keywords']):
            continue
        
        # Filter by keywords in company
        if criteria.get('companies') and all(company_name.lower() not in company.lower() for company_name in criteria['companies']):
            continue
        
        # Filter by minimum salary
        if criteria.get('min_salary'):
            salary_value = parse_salary(salary)
            if not salary_value or salary_value < criteria['min_salary']:
                continue
        
        # Filter by source
        if criteria.get('sources') and source not in criteria['sources']:
            continue
        
        # Filter by freshness
        if criteria.get('max_days_old') and "day" in posted_date:
            try:
                days = int(re.search(r'(\d+)', posted_date).group(1))
                if days > criteria['max_days_old']:
                    continue
            except:
                pass
        
        filtered_jobs.append(job)
    
    return filtered_jobs

# 🚀 Main Execution
def main():
    parser = argparse.ArgumentParser(description='Job Scraper with Filters')
    parser.add_argument('--job_title', type=str, help='Job title to search for')
    parser.add_argument('--location', type=str, help='Location to search in')
    parser.add_argument('--date_posted', type=str, choices=['24h', '3d', '7d', '14d', '30d'], help='Filter by date posted')
    parser.add_argument('--job_type', type=str, choices=['full_time', 'part_time', 'contract', 'temporary', 'internship'], help='Filter by job type')
    parser.add_argument('--experience_level', type=str, choices=['entry', 'mid', 'senior'], help='Filter by experience level')
    parser.add_argument('--salary_min', type=int, help='Minimum salary')
    parser.add_argument('--remote', action='store_true', help='Remote jobs only')
    parser.add_argument('--sources', type=str, nargs='+', choices=['Indeed', 'Glassdoor', 'LinkedIn', 'ZipRecruiter'], help='Sources to scrape')
    parser.add_argument('--keywords', type=str, nargs='+', help='Keywords that must appear in job title')
    parser.add_argument('--companies', type=str, nargs='+', help='Companies to filter by')
    parser.add_argument('--max_days_old', type=int, help='Maximum age of job posting in days')
    
    args = parser.parse_args()
    
# Interactive input mode if no command line arguments
    if len(sys.argv) == 1:
        print("\n📋 Job Search Configuration")
        print("============================")
        
        job_title = input("🔍 Enter job title (required): ").strip()
        if not job_title:
            logger.error("Job title is required.")
            return
        
        location = input("📍 Enter location (leave blank for any): ").strip()
        
        filters = {}
        
        print("\n⏱️ Date Posted Options:")
        print("1. Last 24 hours")
        print("2. Last 3 days")
        print("3. Last 7 days")
        print("4. Last 14 days")
        print("5. Last 30 days")
        print("0. Any time")
        date_choice = input("Select an option (0-5): ").strip()
        date_map = {'1': '24h', '2': '3d', '3': '7d', '4': '14d', '5': '30d'}
        if date_choice in date_map:
            filters['date_posted'] = date_map[date_choice]
        
        print("\n💼 Job Type Options:")
        print("1. Full-time")
        print("2. Part-time")
        print("3. Contract")
        print("4. Temporary")
        print("5. Internship")
        print("0. Any type")
        type_choice = input("Select an option (0-5): ").strip()
        type_map = {'1': 'full_time', '2': 'part_time', '3': 'contract', '4': 'temporary', '5': 'internship'}
        if type_choice in type_map:
            filters['job_type'] = type_map[type_choice]
        
        print("\n🌟 Experience Level Options:")
        print("1. Entry level")
        print("2. Mid level")
        print("3. Senior level")
        print("0. Any level")
        exp_choice = input("Select an option (0-3): ").strip()
        exp_map = {'1': 'entry', '2': 'mid', '3': 'senior'}
        if exp_choice in exp_map:
            filters['experience_level'] = exp_map[exp_choice]
        
        remote_choice = input("\n🏠 Remote jobs only? (y/n): ").strip().lower()
        if remote_choice == 'y':
            filters['remote'] = True
        
        salary_min = input("\n💰 Minimum salary (leave blank for any): ").strip()
        if salary_min and salary_min.isdigit():
            filters['salary_min'] = int(salary_min)
        
        print("\n🔎 Job Sources Options:")
        print("1. Indeed")
        print("2. Glassdoor")
        print("3. LinkedIn")
        print("4. ZipRecruiter")
        print("5. All sources")
        source_choice = input("Select an option (1-5): ").strip()
        if source_choice == '1':
            filters['sources'] = ['Indeed']
        elif source_choice == '2':
            filters['sources'] = ['Glassdoor']
        elif source_choice == '3':
            filters['sources'] = ['LinkedIn']
        elif source_choice == '4':
            filters['sources'] = ['ZipRecruiter']
        else:
            filters['sources'] = ['Indeed', 'Glassdoor', 'LinkedIn', 'ZipRecruiter']
        
        keywords_input = input("\n🔤 Keywords that must appear in job title (comma-separated, leave blank for any): ").strip()
        if keywords_input:
            filters['keywords'] = [k.strip() for k in keywords_input.split(',')]
        
        companies_input = input("\n🏢 Companies to filter by (comma-separated, leave blank for any): ").strip()
        if companies_input:
            filters['companies'] = [c.strip() for c in companies_input.split(',')]
        
        max_days = input("\n📅 Maximum age of job posting in days (leave blank for any): ").strip()
        if max_days and max_days.isdigit():
            filters['max_days_old'] = int(max_days)
    else:
        # Use command line arguments
        job_title = args.job_title
        if not job_title:
            logger.error("Job title is required.")
            return
        
        location = args.location or ""
        
        filters = {
            'date_posted': args.date_posted,
            'job_type': args.job_type,
            'experience_level': args.experience_level,
            'salary_min': args.salary_min,
            'remote': args.remote,
            'sources': args.sources or ['Indeed', 'Glassdoor', 'LinkedIn', 'ZipRecruiter'],
            'keywords': args.keywords,
            'companies': args.companies,
            'max_days_old': args.max_days_old
        }
        # Remove None values
        filters = {k: v for k, v in filters.items() if v is not None}
    
    # Store search parameters
    filters['job_title'] = job_title
    filters['location'] = location
    
    # Log search configuration
    logger.info(f"Starting job search with filters: {filters}")
    print(f"\n🔍 Scraping job listings for '{job_title}' in '{location or 'any location'}'...")
    
    # Setup WebDriver
    try:
        driver = setup_driver()
    except Exception as e:
        logger.error(f"Failed to set up WebDriver: {e}")
        print("❌ Error: Could not initialize web browser. Check your Chrome installation.")
        return
    
    all_jobs = []
    
    # Scrape each requested source
    sources = filters.get('sources', ['Indeed', 'Glassdoor', 'LinkedIn', 'ZipRecruiter'])
    
    try:
        if 'Indeed' in sources:
            indeed_jobs = scrape_indeed(driver, job_title, location, filters)
            all_jobs.extend(indeed_jobs)
            print(f"✅ Found {len(indeed_jobs)} jobs on Indeed")
        
        if 'Glassdoor' in sources:
            glassdoor_jobs = scrape_glassdoor(driver, job_title, location, filters)
            all_jobs.extend(glassdoor_jobs)
            print(f"✅ Found {len(glassdoor_jobs)} jobs on Glassdoor")
        
        if 'LinkedIn' in sources:
            linkedin_jobs = scrape_linkedin(driver, job_title, location, filters)
            all_jobs.extend(linkedin_jobs)
            print(f"✅ Found {len(linkedin_jobs)} jobs on LinkedIn")
        
        if 'ZipRecruiter' in sources:
            ziprecruiter_jobs = scrape_ziprecruiter(driver, job_title, location, filters)
            all_jobs.extend(ziprecruiter_jobs)
            print(f"✅ Found {len(ziprecruiter_jobs)} jobs on ZipRecruiter")
        
    except Exception as e:
        logger.error(f"Error during scraping: {e}")
        print(f"❌ Error occurred during scraping: {e}")
    finally:
        # Close the WebDriver
        driver.quit()
    
    # Apply post-scraping filters
    post_filters = {
        'keywords': filters.get('keywords'),
        'companies': filters.get('companies'),
        'min_salary': filters.get('salary_min'),
        'sources': filters.get('sources'),
        'max_days_old': filters.get('max_days_old')
    }
    post_filters = {k: v for k, v in post_filters.items() if v is not None}
    
    filtered_jobs = filter_jobs(all_jobs, post_filters)
    
    # Generate report
    if filtered_jobs:
        # Save to Google Sheets
        try:
            save_to_google_sheets(filtered_jobs, filters)
            print(f"✅ {len(filtered_jobs)} jobs (out of {len(all_jobs)} total) found and saved to Google Sheets!")
        except Exception as e:
            logger.error(f"Error saving to Google Sheets: {e}")
            print("❌ Could not save to Google Sheets. Saving to CSV instead.")
            
            # Fallback to CSV
            try:
                df = pd.DataFrame(filtered_jobs, columns=["Source", "Job Title", "Company", "Salary", "Job Link", "Date Posted", "Summary"])
                filename = f"job_listings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                df.to_csv(filename, index=False)
                print(f"✅ Job data saved to {filename}")
            except Exception as csv_error:
                logger.error(f"Error saving to CSV: {csv_error}")
                print("❌ Could not save job data.")
    else:
        print("❌ No matching jobs found. Try broadening your search criteria.")
        
    # Print statistics
    print("\n📊 Job Search Statistics:")
    print(f"Total jobs found: {len(all_jobs)}")
    print(f"Jobs after filtering: {len(filtered_jobs)}")
    
    if all_jobs:
        source_counts = {}
        for job in all_jobs:
            source = job[0]
            source_counts[source] = source_counts.get(source, 0) + 1
        
        print("\nJobs by source:")
        for source, count in source_counts.items():
            print(f"- {source}: {count}")
    
    print("\n🏁 Job search complete! Results saved to Google Sheets.")

if __name__ == "__main__":
    # Add missing import
    import sys
    main()