#!/usr/bin/env python3
"""
Anna's Archive Downloader with Manual Cloudflare Click
Pauses for manual human clicks on Cloudflare challenges, then continues automatically
"""

import os
import time
import random
import logging
import keyboard  # pip install keyboard
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

try:
    import undetected_chromedriver as uc

    UNDETECTED_AVAILABLE = True
except ImportError:
    UNDETECTED_AVAILABLE = False
    print("❌ Install: pip install undetected-chromedriver")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ManualClickDownloader:
    def __init__(self, download_dir="downloads", wait_time=30, proxy=None, manual_mode=True):
        """
        Anna's Archive downloader with manual Cloudflare click support

        Args:
            manual_mode (bool): If True, pauses for manual clicks on Cloudflare challenges
        """
        self.base_url = "https://annas-archive.org"
        self.download_dir = download_dir
        self.wait_time = wait_time
        self.proxy = proxy
        self.manual_mode = manual_mode

        os.makedirs(download_dir, exist_ok=True)

        # Setup browser
        self.driver = self._setup_chrome()
        self.wait = WebDriverWait(self.driver, wait_time)

    def _setup_chrome(self):
        """Setup Chrome with working configuration"""
        logger.info("🚀 Setting up Chrome...")

        if not UNDETECTED_AVAILABLE:
            raise ImportError("undetected-chromedriver required: pip install undetected-chromedriver")

        try:
            options = uc.ChromeOptions()

            # Basic stealth options
            stealth_args = [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1366,768"
            ]

            for arg in stealth_args:
                options.add_argument(arg)

            # Proxy if provided
            if self.proxy:
                options.add_argument(f'--proxy-server={self.proxy}')
                logger.info(f"🌐 Using proxy: {self.proxy}")

            # Download settings
            prefs = {
                "download.default_directory": os.path.abspath(self.download_dir),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "plugins.always_open_pdf_externally": True
            }
            options.add_experimental_option("prefs", prefs)

            # Create driver
            driver = uc.Chrome(options=options, use_subprocess=False, version_main=138)

            # Apply basic stealth
            self._apply_basic_stealth(driver)

            logger.info("✅ Chrome setup complete!")
            return driver

        except Exception as e:
            logger.error(f"❌ Chrome setup failed: {e}")
            raise

    def _apply_basic_stealth(self, driver):
        """Apply basic stealth measures"""
        try:
            driver.get("about:blank")

            stealth_script = """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [{name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'}]
                });
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
                if (window.chrome) {
                    Object.defineProperty(window.chrome, 'runtime', {get: () => undefined});
                }
            """

            driver.execute_script(stealth_script)
            logger.info("✅ Basic stealth applied")

        except Exception as e:
            logger.warning(f"⚠️ Stealth application failed: {e}")

    def handle_cloudflare_manual(self):
        """Handle Cloudflare challenges with manual click option"""
        try:
            logger.info("🔍 Checking for Cloudflare challenges...")

            time.sleep(3)  # Let page stabilize

            page_text = self.driver.page_source.lower()
            cloudflare_indicators = [
                "verify you are human",
                "checking your browser",
                "security check",
                "cloudflare",
                "challenge-form"
            ]

            is_cloudflare = any(indicator in page_text for indicator in cloudflare_indicators)

            if is_cloudflare:
                logger.info("🚨 Cloudflare challenge detected!")

                if self.manual_mode:
                    return self._handle_manual_click()
                else:
                    return self._handle_automatic_click()
            else:
                logger.info("✅ No Cloudflare challenge detected")
                return True

        except Exception as e:
            logger.error(f"❌ Cloudflare handling error: {e}")
            return False

    def _handle_manual_click(self):
        """Handle Cloudflare with manual human click"""
        try:
            logger.info("👤 MANUAL CLICK MODE ACTIVATED")
            print("\n" + "=" * 60)
            print("🚨 CLOUDFLARE CHALLENGE DETECTED!")
            print("👆 Please manually click the 'Verify you are human' checkbox")
            print("⏸️  The script will automatically continue after you click")
            print("❌ Press 'q' to quit if needed")
            print("=" * 60)

            # Bring browser to front
            try:
                self.driver.switch_to.window(self.driver.current_window_handle)
                self.driver.execute_script("window.focus();")
            except:
                pass

            # Wait for manual click completion
            return self._wait_for_manual_completion()

        except Exception as e:
            logger.error(f"❌ Manual click handling failed: {e}")
            return False

    def _wait_for_manual_completion(self):
        """Wait for user to manually complete the challenge"""
        try:
            logger.info("⏳ Waiting for manual challenge completion...")

            max_wait = 120  # 2 minutes max wait
            initial_url = self.driver.current_url

            print(f"⏳ Waiting up to {max_wait} seconds for you to click...")

            for i in range(max_wait):
                time.sleep(1)

                # Check for quit command
                if keyboard.is_pressed('q'):
                    logger.info("❌ Manual quit requested")
                    return False

                # Check if challenge is completed
                current_url = self.driver.current_url
                page_text = self.driver.page_source.lower()

                challenge_indicators = [
                    "verify you are human",
                    "checking your browser",
                    "security check"
                ]

                still_challenging = any(indicator in page_text for indicator in challenge_indicators)

                # Check for completion
                if not still_challenging or current_url != initial_url:
                    print("\n✅ CHALLENGE COMPLETED! Continuing automatically...")
                    logger.info("✅ Manual challenge completion detected!")
                    time.sleep(2)  # Brief pause
                    return True

                # Progress indicator every 10 seconds
                if i % 10 == 0 and i > 0:
                    remaining = max_wait - i
                    print(f"⏳ Still waiting... {remaining}s remaining (Press 'q' to quit)")

            print("\n⚠️ TIMEOUT: Challenge not completed within time limit")
            logger.warning("⚠️ Manual completion timeout")
            return False

        except Exception as e:
            logger.error(f"❌ Manual completion wait failed: {e}")
            return False

    def _handle_automatic_click(self):
        """Fallback automatic click handling"""
        try:
            logger.info("🤖 Attempting automatic challenge handling...")

            # Find verification element
            selectors = [
                "input[type='checkbox']",
                ".cf-turnstile input",
                ".challenge-form input"
            ]

            element = None
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for elem in elements:
                        if elem.is_displayed():
                            element = elem
                            break
                    if element:
                        break
                except:
                    continue

            if element:
                logger.info("✅ Found verification element, clicking...")

                self.driver.execute_script("arguments[0].scrollIntoView();", element)
                time.sleep(2)

                try:
                    element.click()
                except:
                    self.driver.execute_script("arguments[0].click();", element)

                logger.info("✅ Automatic click completed")

            # Wait for completion
            return self._wait_for_automatic_completion()

        except Exception as e:
            logger.error(f"❌ Automatic handling failed: {e}")
            return False

    def _wait_for_automatic_completion(self):
        """Wait for automatic challenge completion"""
        try:
            max_wait = 60

            for i in range(max_wait):
                time.sleep(1)

                page_text = self.driver.page_source.lower()
                challenge_indicators = ["verify you are human", "security check"]

                if not any(indicator in page_text for indicator in challenge_indicators):
                    logger.info("✅ Automatic challenge completed!")
                    return True

                if i % 20 == 0 and i > 0:
                    logger.info(f"⏳ Still waiting... ({i}/{max_wait})")

            logger.warning("⚠️ Automatic completion timeout")
            return False

        except Exception as e:
            logger.error(f"❌ Automatic completion failed: {e}")
            return False

    def load_search_terms_from_file(self, filename="test_data.txt"):
        """Load search terms from file"""
        search_terms = []

        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(script_dir, filename)

            if not os.path.exists(file_path):
                logger.warning(f"📁 File {filename} not found")
                return search_terms

            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    term = line.strip().rstrip(',')
                    if term:
                        search_terms.append(term)

            logger.info(f"📚 Loaded {len(search_terms)} search terms")

        except Exception as e:
            logger.error(f"❌ File reading error: {str(e)}")

        return search_terms

    def search_and_download_all(self, search_terms):
        """Main downloading method with manual click support"""
        if not search_terms:
            logger.warning("⚠️ No search terms provided")
            return

        successful_downloads = []
        failed_downloads = []

        logger.info(f"🚀 Starting downloads with manual click mode...")

        for i, term in enumerate(search_terms, 1):
            logger.info(f"\n{'=' * 60}")
            logger.info(f"🔍 Processing {i}/{len(search_terms)}: '{term}'")
            logger.info(f"{'=' * 60}")

            try:
                if self.process_single_search(term):
                    successful_downloads.append(term)
                    logger.info(f"✅ SUCCESS: '{term}'")
                else:
                    failed_downloads.append(term)
                    logger.warning(f"❌ FAILED: '{term}'")
            except Exception as e:
                logger.error(f"💥 ERROR: {str(e)}")
                failed_downloads.append(term)

            # Delay between searches
            if i < len(search_terms):
                delay = random.uniform(8, 15)
                logger.info(f"⏳ Waiting {delay:.1f}s before next search...")
                time.sleep(delay)

        # Summary
        logger.info(f"\n{'=' * 60}")
        logger.info(f"📊 DOWNLOAD SUMMARY")
        logger.info(f"{'=' * 60}")
        logger.info(f"✅ Successful: {len(successful_downloads)}")
        logger.info(f"❌ Failed: {len(failed_downloads)}")

        if successful_downloads:
            logger.info(f"\n✅ SUCCESSFUL:")
            for term in successful_downloads:
                logger.info(f"  ✓ {term}")

        if failed_downloads:
            logger.info(f"\n❌ FAILED:")
            for term in failed_downloads:
                logger.info(f"  ✗ {term}")

    def process_single_search(self, search_term):
        """Process single search with manual click support"""
        try:
            logger.info(f"🌐 Navigating to Anna's Archive...")

            # Navigate to site
            self.driver.get(self.base_url)

            # Handle Cloudflare with manual click
            if not self.handle_cloudflare_manual():
                logger.warning("⚠️ Cloudflare handling failed")
                return False

            # Continue with search
            time.sleep(random.uniform(2, 4))

            # Find search box
            search_box = None
            search_selectors = [
                "input[placeholder*='Title, author, DOI, ISBN, MD5']",
                "input[type='search']",
                "input[name='q']"
            ]

            for selector in search_selectors:
                try:
                    search_box = self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"🔍 Found search box")
                    break
                except TimeoutException:
                    continue

            if not search_box:
                logger.error("❌ Search box not found")
                return False

            # Perform search
            search_box.clear()
            time.sleep(1)

            # Type search term
            for char in search_term:
                search_box.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))

            time.sleep(random.uniform(1, 2))
            search_box.send_keys(Keys.RETURN)

            # Wait for results
            logger.info("⏳ Waiting for search results...")
            time.sleep(random.uniform(5, 8))

            # Handle Cloudflare on search results
            if not self.handle_cloudflare_manual():
                logger.warning("⚠️ Search results Cloudflare handling failed")

            # Find first result
            first_result = None
            result_selectors = [
                "h3 a",
                "a[href*='/md5/']",
                ".text-xl a"
            ]

            for selector in result_selectors:
                try:
                    results = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if results:
                        first_result = results[0]
                        logger.info(f"📖 Found result")
                        break
                except:
                    continue

            if not first_result:
                logger.error("❌ No results found")
                return False

            # Click result
            logger.info(f"🖱️ Clicking result...")
            self.driver.execute_script("arguments[0].scrollIntoView();", first_result)
            time.sleep(2)

            try:
                first_result.click()
            except:
                self.driver.execute_script("arguments[0].click();", first_result)

            time.sleep(random.uniform(3, 6))

            # Attempt download
            return self.attempt_download()

        except Exception as e:
            logger.error(f"❌ Search processing error: {str(e)}")
            return False

    def attempt_download(self):
        """Attempt download with manual click support"""
        try:
            logger.info("📥 Attempting download...")

            # Handle Cloudflare on book page
            if not self.handle_cloudflare_manual():
                logger.warning("⚠️ Book page Cloudflare handling failed")

            time.sleep(random.uniform(2, 4))

            # Find download link
            download_selectors = [
                "a[href*='slow_download']",
                "a[href*='fast_download']",
                "a[href*='download']"
            ]

            download_link = None
            for selector in download_selectors:
                try:
                    download_link = self.driver.find_element(By.CSS_SELECTOR, selector)
                    logger.info(f"📥 Found download link")
                    break
                except:
                    continue

            if not download_link:
                # Search all links
                all_links = self.driver.find_elements(By.TAG_NAME, "a")
                for link in all_links:
                    href = link.get_attribute('href')
                    if href and 'download' in href.lower():
                        download_link = link
                        break

            if download_link:
                logger.info("✅ Clicking download link")
                self.driver.execute_script("arguments[0].scrollIntoView();", download_link)
                time.sleep(2)

                try:
                    download_link.click()
                except:
                    self.driver.execute_script("arguments[0].click();", download_link)

                # Handle download page
                return self.handle_download_page()
            else:
                logger.warning("❌ No download links found")
                return False

        except Exception as e:
            logger.error(f"❌ Download attempt failed: {str(e)}")
            return False

    def handle_download_page(self):
        """Handle download page with manual click support"""
        try:
            logger.info("📄 Handling download page...")

            # Handle Cloudflare on download page
            if not self.handle_cloudflare_manual():
                logger.warning("⚠️ Download page Cloudflare handling failed")

            time.sleep(random.uniform(3, 6))

            # Check for wait page
            page_text = self.driver.page_source.lower()
            wait_indicators = ["please wait", "seconds", "preparing"]

            if any(indicator in page_text for indicator in wait_indicators):
                logger.info("⏳ Wait page detected, waiting for download...")

                # Wait for download elements
                max_wait = 120
                for i in range(max_wait):
                    time.sleep(1)

                    try:
                        # Look for download elements
                        download_elements = self.driver.find_elements(By.XPATH,
                                                                      "//a[contains(@href, '.pdf') or contains(@href, '.epub') or contains(text(), 'Download') or contains(text(), 'Click here')]")

                        if download_elements:
                            logger.info(f"📥 Found download elements")
                            for element in download_elements:
                                try:
                                    self.driver.execute_script("arguments[0].scrollIntoView();", element)
                                    time.sleep(1)
                                    element.click()
                                    logger.info("✅ Download initiated!")
                                    time.sleep(10)  # Wait for download
                                    return True
                                except:
                                    continue

                    except:
                        continue

                    if i % 30 == 0 and i > 0:
                        logger.info(f"⏳ Still waiting... ({i}/{max_wait})")

                logger.warning("⚠️ Download timeout")
                return False
            else:
                logger.info("✅ Direct download page")
                time.sleep(10)  # Wait for download
                return True

        except Exception as e:
            logger.error(f"❌ Download page error: {str(e)}")
            return False

    def close(self):
        """Close browser"""
        if hasattr(self, 'driver'):
            self.driver.quit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Main execution
if __name__ == "__main__":
    print("🚀 MANUAL CLICK ANNA'S ARCHIVE DOWNLOADER")
    print("=" * 60)
    print("✅ Automatic Cloudflare detection")
    print("👆 Manual human clicks for verification")
    print("🔄 Automatic continuation after clicks")
    print("❌ Press 'q' during challenges to quit")
    print("=" * 60)
    print()

    # Configuration
    MANUAL_MODE = True  # Set to False for automatic clicking
    PROXY = None  # Set proxy if needed

    try:
        # Install keyboard if not available
        try:
            import keyboard
        except ImportError:
            print("❌ Installing keyboard library...")
            os.system("pip install keyboard")
            import keyboard

        with ManualClickDownloader(
                download_dir="../../annas_archive_downloads",
                proxy=PROXY,
                manual_mode=MANUAL_MODE
        ) as downloader:

            # Load search terms
            search_terms = downloader.load_search_terms_from_file("test_data.txt")

            if search_terms:
                print(f"📚 Loaded {len(search_terms)} search terms")
                print("👆 You'll be prompted to manually click Cloudflare challenges")
                print("🔄 Script continues automatically after your clicks")
                print()

                # Start downloading
                downloader.search_and_download_all(search_terms)

            else:
                print("❌ No search terms found in test_data.txt")

                # Fallback
                fallback_terms = ["python programming", "machine learning"]
                print("🔄 Using fallback terms for testing...")
                downloader.search_and_download_all(fallback_terms)

            print("\n🎉 Download session complete!")

    except KeyboardInterrupt:
        print("\n⏹️ Download interrupted")
    except Exception as e:
        print(f"\n💥 Error: {e}")
        print("💡 Make sure to install: pip install keyboard undetected-chromedriver")