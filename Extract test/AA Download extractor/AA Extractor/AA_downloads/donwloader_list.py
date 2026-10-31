#!/usr/bin/env python3
"""
Anna's Archive Bulk Downloader
Automates searching and downloading from Anna's Archive
Reads search terms from test_data.txt file
"""

import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.firefox import GeckoDriverManager
from urllib.parse import urljoin, urlparse
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AnnasArchiveDownloader:
    def __init__(self, download_dir="downloads", headless=False, wait_time=10):
        """
        Initialize the downloader

        Args:
            download_dir (str): Directory to save downloads
            headless (bool): Run browser in headless mode
            wait_time (int): Maximum wait time for elements
        """
        self.base_url = "https://annas-archive.org"
        self.download_dir = download_dir
        self.wait_time = wait_time

        # Create download directory
        os.makedirs(download_dir, exist_ok=True)

        # Setup Firefox options with better anti-detection
        firefox_options = Options()
        if headless:
            firefox_options.add_argument("--headless")

        # Add user agent and other options to appear more human
        firefox_options.set_preference("general.useragent.override",
                                       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        firefox_options.set_preference("dom.webdriver.enabled", False)
        firefox_options.set_preference("useAutomationExtension", False)

        # Set Firefox download preferences
        firefox_options.set_preference("browser.download.folderList", 2)
        firefox_options.set_preference("browser.download.dir", os.path.abspath(download_dir))
        firefox_options.set_preference("browser.download.useDownloadDir", True)
        firefox_options.set_preference("browser.helperApps.neverAsk.saveToDisk",
                                       "application/pdf,application/epub+zip,application/x-mobipocket-ebook,application/octet-stream")
        firefox_options.set_preference("browser.download.manager.showWhenStarting", False)
        firefox_options.set_preference("pdfjs.disabled", True)  # Disable PDF viewer to force download

        # Initialize driver with better stealth settings
        executable_path = GeckoDriverManager().install()
        self.driver = webdriver.Firefox(executable_path=executable_path, options=firefox_options)

        # Additional stealth measures
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.wait = WebDriverWait(self.driver, wait_time)

    def load_search_terms_from_file(self, filename="test_data.txt"):
        """
        Load search terms from a text file

        Args:
            filename (str): Name of the file containing search terms

        Returns:
            list: List of search terms, or empty list if file not found
        """
        search_terms = []

        try:
            # Get the directory where the script is located
            script_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(script_dir, filename)

            if not os.path.exists(file_path):
                logger.warning(f"File {filename} not found in {script_dir}")
                return search_terms

            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    # Strip whitespace and commas, skip empty lines
                    term = line.strip().rstrip(',')
                    if term:
                        search_terms.append(term)

            logger.info(f"Loaded {len(search_terms)} search terms from {filename}")

        except Exception as e:
            logger.error(f"Error reading file {filename}: {str(e)}")

        return search_terms

    def search_and_download(self, search_terms):
        """
        Main method to process a list of search terms

        Args:
            search_terms (list): List of strings to search for
        """
        if not search_terms:
            logger.warning("No search terms provided")
            return

        successful_downloads = []
        failed_downloads = []

        for i, term in enumerate(search_terms, 1):
            logger.info(f"Processing {i}/{len(search_terms)}: '{term}'")
            try:
                if self.process_single_search(term):
                    successful_downloads.append(term)
                    logger.info(f"Successfully processed: '{term}'")
                else:
                    failed_downloads.append(term)
                    logger.warning(f"Failed to process: '{term}'")
            except Exception as e:
                logger.error(f"Error processing '{term}': {str(e)}")
                failed_downloads.append(term)

            # Add delay between searches to be respectful
            time.sleep(2)

        # Print summary
        logger.info(f"\nSummary:")
        logger.info(f"Successful: {len(successful_downloads)}")
        logger.info(f"Failed: {len(failed_downloads)}")

        if failed_downloads:
            logger.info(f"Failed terms: {failed_downloads}")

    def process_single_search(self, search_term):
        """
        Process a single search term

        Args:
            search_term (str): The term to search for

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Navigating to Anna's Archive...")
            # Navigate to Anna's Archive
            self.driver.get(self.base_url)

            # Wait for page to load and take a screenshot for debugging
            time.sleep(5)

            # Try multiple search box selectors
            search_box = None
            search_selectors = [
                "input[placeholder*='Title, author, DOI, ISBN, MD5']",
                "input[type='search']",
                "input[name='q']",
                ".search-input",
                "#search-input",
                "input[placeholder*='search']",
                "input.form-control"
            ]

            for selector in search_selectors:
                try:
                    search_box = self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"Found search box with selector: {selector}")
                    break
                except TimeoutException:
                    logger.debug(f"Search selector failed: {selector}")
                    continue

            if not search_box:
                logger.error("Could not find search box with any selector")
                # Print page source for debugging
                logger.debug(f"Page title: {self.driver.title}")
                return False

            # Clear and enter search term
            search_box.clear()
            search_box.send_keys(search_term)
            search_box.send_keys(Keys.RETURN)

            # Wait for search results with longer timeout
            logger.info("Waiting for search results...")
            time.sleep(8)  # Increased wait time

            # Try multiple result selectors
            first_result = None
            result_selectors = [
                "h3 a",
                ".text-xl a",
                "a[href*='/md5/']",
                ".result-title a",
                ".search-result a",
                "h2 a",
                "h4 a",
                ".book-title a",
                "a:contains('PDF')",
                "div.mb-4 a"  # Common class pattern
            ]

            for selector in result_selectors:
                try:
                    if selector.startswith("a:contains"):
                        # Handle text-based selector differently
                        links = self.driver.find_elements(By.TAG_NAME, "a")
                        for link in links:
                            if "pdf" in link.text.lower() or len(link.text) > 10:
                                first_result = link
                                break
                    else:
                        results = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if results:
                            first_result = results[0]
                            logger.info(f"Found result with selector: {selector}")
                            break
                except Exception as e:
                    logger.debug(f"Result selector failed {selector}: {str(e)}")
                    continue

            if not first_result:
                logger.error("Could not find any search results")
                # Log available links for debugging
                all_links = self.driver.find_elements(By.TAG_NAME, "a")
                logger.debug(f"Found {len(all_links)} total links on page")
                for i, link in enumerate(all_links[:10]):  # Show first 10 links
                    logger.debug(f"Link {i}: {link.get_attribute('href')} - Text: {link.text[:50]}")
                return False

            # Click on the first result
            logger.info(f"Clicking on result: {first_result.text[:50]}")
            self.driver.execute_script("arguments[0].scrollIntoView();", first_result)
            time.sleep(2)
            first_result.click()

            # Wait for the book page to load
            time.sleep(5)

            # Try to download
            return self.attempt_download()

        except TimeoutException:
            logger.error(f"Timeout waiting for elements for search: '{search_term}'")
            return False
        except NoSuchElementException:
            logger.error(f"Could not find required elements for search: '{search_term}'")
            return False
        except Exception as e:
            logger.error(f"Unexpected error for search '{search_term}': {str(e)}")
            return False

    def handle_cloudflare_check(self):
        """
        Handle Cloudflare security check
        """
        try:
            # Wait for Cloudflare check to complete
            logger.info("Checking for Cloudflare security verification...")

            # Look for common Cloudflare elements
            cloudflare_indicators = [
                "Verify you are human",
                "Checking your browser",
                "Please wait while we verify",
                "Security check"
            ]

            page_text = self.driver.page_source.lower()
            is_cloudflare = any(indicator.lower() in page_text for indicator in cloudflare_indicators)

            if is_cloudflare:
                logger.info("Cloudflare check detected. Waiting for completion...")

                # Wait up to 30 seconds for Cloudflare to complete
                for i in range(30):
                    time.sleep(1)
                    current_url = self.driver.current_url
                    page_text = self.driver.page_source.lower()

                    # Check if we've moved past the Cloudflare page
                    if not any(indicator.lower() in page_text for indicator in cloudflare_indicators):
                        logger.info("Cloudflare check completed successfully")
                        return True

                    # Check if URL changed (sometimes indicates success)
                    if i > 0 and current_url != getattr(self, '_last_url', current_url):
                        logger.info("URL changed - Cloudflare check may have completed")
                        return True

                    self._last_url = current_url

                logger.warning("Cloudflare check may still be in progress")
                return False
            else:
                return True

        except Exception as e:
            logger.error(f"Error handling Cloudflare check: {str(e)}")
            return False

    def attempt_download(self):
        """
        Attempt to download from the current page

        Returns:
            bool: True if download was initiated, False otherwise
        """
        try:
            # Handle Cloudflare check first
            if not self.handle_cloudflare_check():
                logger.warning("Cloudflare check not completed, but continuing...")

            time.sleep(3)  # Additional wait after Cloudflare

            # Look for download options with more specific selectors
            download_selectors = [
                "a[href*='slow_download']",  # Slow download links
                "a[href*='fast_download']",  # Fast download links
                "a[href*='download']",  # General download links
                "a:contains('Slow Partner Server')",
                "a:contains('Fast Partner Server')",
                "a:contains('Download')",
                ".download-link",
                "button:contains('Download')"
            ]

            download_link = None
            for selector in download_selectors:
                try:
                    if ":contains(" in selector:
                        # Handle text-based selector
                        text_to_find = selector.split(":contains('")[1].split("')")[0]
                        elements = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{text_to_find}')]")
                        for elem in elements:
                            if elem.tag_name.lower() in ['a', 'button']:
                                download_link = elem
                                logger.info(f"Found download link with text: {text_to_find}")
                                break
                    else:
                        download_link = self.driver.find_element(By.CSS_SELECTOR, selector)
                        logger.info(f"Found download link with selector: {selector}")

                    if download_link:
                        break
                except NoSuchElementException:
                    continue

            if not download_link:
                # Log available links for debugging
                logger.warning("No specific download links found. Checking all links...")
                all_links = self.driver.find_elements(By.TAG_NAME, "a")
                for link in all_links:
                    href = link.get_attribute('href')
                    text = link.text.strip()
                    if href and ('download' in href.lower() or 'download' in text.lower()):
                        download_link = link
                        logger.info(f"Found potential download link: {text} - {href}")
                        break

            if download_link:
                # Scroll to element and click
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", download_link)
                time.sleep(2)

                # Try different click methods
                try:
                    download_link.click()
                except Exception as e:
                    logger.info(f"Regular click failed, trying JavaScript click: {e}")
                    self.driver.execute_script("arguments[0].click();", download_link)

                # Handle the download page
                self.handle_download_page()
                return True
            else:
                logger.warning("No download links found on the page")
                # Log current URL and page title for debugging
                logger.info(f"Current URL: {self.driver.current_url}")
                logger.info(f"Page title: {self.driver.title}")
                return False

        except Exception as e:
            logger.error(f"Error attempting download: {str(e)}")
            return False

    def handle_download_page(self):
        """
        Handle download pages that may have wait times, Cloudflare checks, or additional steps
        """
        try:
            # Handle Cloudflare check on download page
            self.handle_cloudflare_check()

            # Wait for any "Please wait" messages or countdowns
            time.sleep(5)

            # Check if we're on a wait page or download verification page
            wait_indicators = [
                "Please wait",
                "seconds",
                "Preparing your download",
                "Processing",
                "Verify you are human"
            ]

            page_text = self.driver.page_source.lower()
            is_wait_page = any(indicator.lower() in page_text for indicator in wait_indicators)

            if is_wait_page:
                logger.info("Detected wait/verification page, waiting for download to become available...")

                # Wait for up to 120 seconds for the download to become available
                for i in range(120):
                    time.sleep(1)

                    # Look for actual download buttons or links
                    download_elements = []

                    # Try multiple approaches to find download
                    try:
                        # Look for direct file download links
                        direct_downloads = self.driver.find_elements(By.XPATH,
                                                                     "//a[contains(@href, '.pdf') or contains(@href, '.epub') or contains(@href, '.mobi') or contains(@href, '.djvu')]")
                        download_elements.extend(direct_downloads)

                        # Look for download buttons
                        download_buttons = self.driver.find_elements(By.XPATH,
                                                                     "//button[contains(text(), 'Download')] | //a[contains(text(), 'Download')]")
                        download_elements.extend(download_buttons)

                        # Look for "Click here" or similar text
                        click_links = self.driver.find_elements(By.XPATH,
                                                                "//a[contains(text(), 'Click here') or contains(text(), 'click here')]")
                        download_elements.extend(click_links)

                    except Exception as e:
                        logger.debug(f"Error finding download elements: {e}")
                        continue

                    if download_elements:
                        logger.info(f"Found {len(download_elements)} potential download elements")
                        for element in download_elements:
                            try:
                                # Scroll to element and click
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                                time.sleep(1)

                                # Try clicking
                                element.click()
                                logger.info("Download initiated successfully")

                                # Wait a bit more for download to start
                                time.sleep(10)
                                return

                            except Exception as e:
                                logger.debug(f"Failed to click download element: {e}")
                                continue

                    # Check if URL changed (might indicate download started)
                    current_url = self.driver.current_url
                    if hasattr(self, '_download_page_url') and current_url != self._download_page_url:
                        logger.info("URL changed - download may have started")
                        time.sleep(5)
                        return

                    self._download_page_url = current_url

                logger.warning("Timeout waiting for download to become available")
            else:
                logger.info("No wait page detected, download may have started immediately")
                time.sleep(10)  # Give time for download to start

        except Exception as e:
            logger.error(f"Error handling download page: {str(e)}")

    def close(self):
        """Clean up and close the browser"""
        if hasattr(self, 'driver'):
            self.driver.quit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Example usage
if __name__ == "__main__":
    # Create downloader instance
    with AnnasArchiveDownloader(download_dir="annas_archive_downloads", headless=False) as downloader:
        # Load search terms from file
        search_terms = downloader.load_search_terms_from_file("test_data.txt")

        if search_terms:
            # Process the search terms
            downloader.search_and_download(search_terms)
        else:
            logger.error("No search terms loaded. Please check that test_data.txt exists and contains search terms.")
            # Fallback to example terms if file doesn't exist
            fallback_terms = [
                "python programming",
                "machine learning",
                "data structures algorithms",
            ]
            logger.info("Using fallback search terms...")
            downloader.search_and_download(fallback_terms)