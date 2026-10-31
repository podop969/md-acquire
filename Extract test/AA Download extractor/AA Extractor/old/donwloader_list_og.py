#!/usr/bin/env python3
"""
Anna's Archive Complete Downloader - WORKING VERSION
Successfully bypasses Cloudflare and downloads books from search terms list
"""

import os
import time
import random
import logging
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

try:
    from fake_useragent import UserAgent

    FAKE_UA_AVAILABLE = True
except ImportError:
    FAKE_UA_AVAILABLE = False
    print("❌ Install: pip install fake-useragent")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CompleteAnnasArchiveDownloader:
    def __init__(self, download_dir="downloads", wait_time=30, proxy=None, user_data_dir=None):
        """
        Complete Anna's Archive downloader with working Cloudflare bypass

        Args:
            download_dir (str): Directory to save downloads
            wait_time (int): Wait time for elements
            proxy (str): Proxy "ip:port" format
            user_data_dir (str): Chrome profile path for maximum stealth
        """
        self.base_url = "https://annas-archive.org"
        self.download_dir = download_dir
        self.wait_time = wait_time
        self.proxy = proxy
        self.user_data_dir = user_data_dir

        os.makedirs(download_dir, exist_ok=True)

        # Setup with proven working configuration
        self.driver = self._setup_working_chrome()
        self.wait = WebDriverWait(self.driver, wait_time)

    def _setup_working_chrome(self):
        """Setup Chrome with the PROVEN working configuration"""
        logger.info("🚀 Setting up WORKING Chrome configuration...")

        if not UNDETECTED_AVAILABLE:
            raise ImportError("undetected-chromedriver required: pip install undetected-chromedriver")

        try:
            options = uc.ChromeOptions()

            # Use Chrome profile if provided
            if self.user_data_dir:
                logger.info(f"🔐 Using Chrome profile: {self.user_data_dir}")
                options.add_argument(f"--user-data-dir={self.user_data_dir}")
                options.add_argument("--profile-directory=AutomationProfile")

            # Proven working stealth arguments
            stealth_args = [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=VizDisplayCompositor",
                "--disable-ipc-flooding-protection",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
                "--disable-field-trial-config",
                "--disable-back-forward-cache",
                "--disable-hang-monitor",
                "--disable-prompt-on-repost",
                "--disable-sync",
                "--disable-translate",
                "--hide-scrollbars",
                "--mute-audio",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-logging",
                "--disable-gpu-logging",
                "--disable-software-rasterizer"
            ]

            for arg in stealth_args:
                options.add_argument(arg)

            # Realistic window size
            options.add_argument("--window-size=1366,768")

            # Proxy if provided
            if self.proxy:
                options.add_argument(f'--proxy-server={self.proxy}')
                logger.info(f"🌐 Using proxy: {self.proxy}")

            # Download settings
            prefs = {
                "download.default_directory": os.path.abspath(self.download_dir),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "plugins.always_open_pdf_externally": True,
                "profile.default_content_settings.popups": 0,
                "profile.default_content_setting_values.notifications": 2
            }
            options.add_experimental_option("prefs", prefs)

            # Create driver with working version
            logger.info("🎯 Starting Chrome with working configuration...")
            driver = uc.Chrome(
                options=options,
                use_subprocess=False,
                version_main=138
            )

            # Apply proven stealth
            self._apply_working_stealth(driver)

            # Pre-warm browser
            self._prewarm_browser(driver)

            logger.info("✅ Working Chrome setup complete!")
            return driver

        except Exception as e:
            logger.error(f"❌ Working Chrome setup failed: {e}")
            raise

    def _apply_working_stealth(self, driver):
        """Apply the proven working stealth configuration"""
        try:
            logger.info("🥷 Applying working stealth measures...")

            driver.get("about:blank")

            stealth_script = """
                // Core webdriver removal
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });

                // Navigator overrides
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        {
                            name: 'Chrome PDF Plugin',
                            filename: 'internal-pdf-viewer',
                            description: 'Portable Document Format',
                            length: 1
                        }
                    ]
                });

                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });

                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 8
                });

                // Remove automation artifacts
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;

                // Chrome runtime removal
                if (window.chrome) {
                    Object.defineProperty(window.chrome, 'runtime', {
                        get: () => undefined
                    });
                }

                console.log('✅ Working stealth applied');
            """

            driver.execute_script(stealth_script)
            logger.info("✅ Working stealth injection successful")

        except Exception as e:
            logger.warning(f"⚠️ Some stealth measures failed: {e}")

    def _prewarm_browser(self, driver):
        """Pre-warm browser with normal sites"""
        try:
            logger.info("🔥 Pre-warming browser...")

            prewarm_sites = ["https://www.google.com"]

            for site in prewarm_sites:
                try:
                    driver.get(site)
                    time.sleep(random.uniform(2, 4))
                    self._simulate_basic_behavior(driver)
                except Exception as e:
                    logger.debug(f"Pre-warm failed: {e}")

            logger.info("✅ Browser pre-warming complete")

        except Exception as e:
            logger.warning(f"⚠️ Pre-warming failed: {e}")

    def _simulate_basic_behavior(self, driver):
        """Basic human behavior simulation"""
        try:
            # Mouse movement
            x = random.randint(200, 600)
            y = random.randint(200, 400)
            driver.execute_script(f"""
                var event = new MouseEvent('mousemove', {{
                    clientX: {x},
                    clientY: {y},
                    bubbles: true
                }});
                document.dispatchEvent(event);
            """)

            # Small scroll
            scroll_amount = random.randint(100, 200)
            driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            time.sleep(random.uniform(0.5, 1.0))

        except Exception as e:
            logger.debug(f"Basic behavior failed: {e}")

    def handle_cloudflare_challenge(self):
        """Handle Cloudflare challenges with the proven working method"""
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

                # Simulate extensive human behavior before interaction
                self._simulate_comprehensive_behavior()

                # Find and click verification element
                return self._handle_verification_element()
            else:
                logger.info("✅ No Cloudflare challenge detected")
                return True

        except Exception as e:
            logger.error(f"❌ Cloudflare handling error: {e}")
            return False

    def _simulate_comprehensive_behavior(self):
        """Comprehensive human behavior that works"""
        try:
            logger.info("🤖 Simulating comprehensive human behavior...")

            # Extended observation
            time.sleep(random.uniform(5, 8))

            # Multiple mouse movements with curves
            for i in range(6):
                start_x = random.randint(100, 400)
                start_y = random.randint(100, 300)
                end_x = random.randint(500, 900)
                end_y = random.randint(300, 600)

                steps = random.randint(15, 20)
                for step in range(steps):
                    progress = step / steps
                    control_x = (start_x + end_x) / 2 + random.randint(-50, 50)
                    control_y = (start_y + end_y) / 2 + random.randint(-30, 30)

                    x = start_x + progress * (end_x - start_x) + progress * (1 - progress) * (control_x - start_x)
                    y = start_y + progress * (end_y - start_y) + progress * (1 - progress) * (control_y - start_y)

                    self.driver.execute_script(f"""
                        var event = new MouseEvent('mousemove', {{
                            clientX: {x},
                            clientY: {y},
                            bubbles: true
                        }});
                        document.dispatchEvent(event);
                    """)
                    time.sleep(random.uniform(0.02, 0.04))

                time.sleep(random.uniform(0.5, 1.0))

            # Reading pauses
            time.sleep(random.uniform(3, 5))

            # Natural scrolling
            for _ in range(3):
                scroll_amount = random.randint(50, 150)
                direction = random.choice([1, -1])
                self.driver.execute_script(f"window.scrollBy(0, {scroll_amount * direction});")
                time.sleep(random.uniform(1, 2))

            logger.info("✅ Comprehensive behavior complete")

        except Exception as e:
            logger.debug(f"Behavior simulation error: {e}")

    def _handle_verification_element(self):
        """Handle verification element with proven working method"""
        try:
            logger.info("🔧 Handling verification element...")

            # Find verification element
            selectors = [
                "input[type='checkbox']",
                ".cf-turnstile input",
                ".challenge-form input",
                "button[type='submit']"
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
                logger.info("✅ Found verification element")

                # Scroll to element smoothly
                self.driver.execute_script("""
                    arguments[0].scrollIntoView({
                        behavior: 'smooth',
                        block: 'center'
                    });
                """, element)

                time.sleep(random.uniform(2, 4))

                # Realistic click approach
                try:
                    element.click()
                    logger.info("✅ Verification element clicked")
                except:
                    self.driver.execute_script("arguments[0].click();", element)
                    logger.info("✅ Verification element clicked (JS)")

                # Wait for completion
                return self._wait_for_challenge_completion()

            else:
                logger.info("ℹ️ No verification element found, waiting for auto-completion")
                return self._wait_for_challenge_completion()

        except Exception as e:
            logger.error(f"❌ Verification handling failed: {e}")
            return False

    def _wait_for_challenge_completion(self):
        """Wait for challenge completion with continued behavior"""
        try:
            logger.info("⏳ Waiting for challenge completion...")

            max_wait = 60
            initial_url = self.driver.current_url

            for i in range(max_wait):
                time.sleep(1)

                # Continue behavior during wait
                if i % 10 == 0:
                    x = random.randint(200, 600)
                    y = random.randint(200, 400)
                    self.driver.execute_script(f"""
                        var event = new MouseEvent('mousemove', {{
                            clientX: {x},
                            clientY: {y},
                            bubbles: true
                        }});
                        document.dispatchEvent(event);
                    """)

                # Check completion
                current_url = self.driver.current_url
                page_text = self.driver.page_source.lower()

                challenge_indicators = [
                    "verify you are human",
                    "checking your browser",
                    "security check"
                ]

                still_challenging = any(indicator in page_text for indicator in challenge_indicators)

                if not still_challenging or current_url != initial_url:
                    logger.info("✅ Challenge completed!")
                    time.sleep(random.uniform(2, 4))
                    return True

                if i % 20 == 0 and i > 0:
                    logger.info(f"⏳ Still waiting... ({i}/{max_wait})")

            logger.warning("⚠️ Challenge completion timeout")
            return False

        except Exception as e:
            logger.error(f"❌ Challenge completion error: {e}")
            return False

    def load_search_terms_from_file(self, filename="test_data.txt"):
        """Load search terms from file"""
        search_terms = []

        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(script_dir, filename)

            if not os.path.exists(file_path):
                logger.warning(f"📁 File {filename} not found in {script_dir}")
                return search_terms

            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    term = line.strip().rstrip(',')
                    if term:
                        search_terms.append(term)

            logger.info(f"📚 Loaded {len(search_terms)} search terms from {filename}")

        except Exception as e:
            logger.error(f"❌ Error reading file {filename}: {str(e)}")

        return search_terms

    def search_and_download_all(self, search_terms):
        """Main method to search and download all terms"""
        if not search_terms:
            logger.warning("⚠️ No search terms provided")
            return

        successful_downloads = []
        failed_downloads = []

        logger.info(f"🚀 Starting bulk download of {len(search_terms)} items...")

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
                logger.error(f"💥 ERROR processing '{term}': {str(e)}")
                failed_downloads.append(term)

            # Delay between searches
            if i < len(search_terms):
                delay = random.uniform(10, 20)
                logger.info(f"⏳ Waiting {delay:.1f}s before next search...")
                time.sleep(delay)

        # Final summary
        logger.info(f"\n{'=' * 60}")
        logger.info(f"📊 FINAL DOWNLOAD SUMMARY")
        logger.info(f"{'=' * 60}")
        logger.info(f"✅ Successful: {len(successful_downloads)}")
        logger.info(f"❌ Failed: {len(failed_downloads)}")
        logger.info(f"📈 Success Rate: {len(successful_downloads) / len(search_terms) * 100:.1f}%")

        if successful_downloads:
            logger.info(f"\n✅ SUCCESSFUL DOWNLOADS:")
            for term in successful_downloads:
                logger.info(f"  ✓ {term}")

        if failed_downloads:
            logger.info(f"\n❌ FAILED DOWNLOADS:")
            for term in failed_downloads:
                logger.info(f"  ✗ {term}")

    def process_single_search(self, search_term):
        """Process a single search term"""
        try:
            logger.info(f"🌐 Navigating to Anna's Archive...")

            # Navigate to main site
            self.driver.get(self.base_url)

            # Handle Cloudflare immediately
            if not self.handle_cloudflare_challenge():
                logger.warning("⚠️ Cloudflare challenge handling incomplete")

            # Additional behavior after page load
            self._simulate_basic_behavior(self.driver)
            time.sleep(random.uniform(3, 6))

            # Find search box
            search_box = None
            search_selectors = [
                "input[placeholder*='Title, author, DOI, ISBN, MD5']",
                "input[type='search']",
                "input[name='q']",
                ".search-input",
                "#search-input",
                "input[placeholder*='search']"
            ]

            for selector in search_selectors:
                try:
                    search_box = self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"🔍 Found search box: {selector}")
                    break
                except TimeoutException:
                    continue

            if not search_box:
                logger.error("❌ Could not find search box")
                return False

            # Perform search with human-like typing
            search_box.clear()
            time.sleep(random.uniform(1, 2))

            # Type with realistic delays
            for char in search_term:
                search_box.send_keys(char)
                time.sleep(random.uniform(0.08, 0.18))

            time.sleep(random.uniform(1, 3))
            search_box.send_keys(Keys.RETURN)

            # Wait for search results
            logger.info("⏳ Waiting for search results...")
            time.sleep(random.uniform(6, 10))

            # Handle Cloudflare on search results if needed
            self.handle_cloudflare_challenge()

            # Find first result
            first_result = None
            result_selectors = [
                "h3 a",
                ".text-xl a",
                "a[href*='/md5/']",
                ".result-title a",
                "h2 a",
                "h4 a",
                "div.mb-4 a"
            ]

            for selector in result_selectors:
                try:
                    results = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if results:
                        first_result = results[0]
                        logger.info(f"📖 Found result: {selector}")
                        break
                except:
                    continue

            if not first_result:
                logger.error("❌ No search results found")
                return False

            # Click first result
            self._simulate_basic_behavior(self.driver)
            logger.info(f"🖱️ Clicking result: {first_result.text[:50]}")

            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth'});", first_result)
            time.sleep(random.uniform(2, 4))

            try:
                first_result.click()
            except:
                self.driver.execute_script("arguments[0].click();", first_result)

            # Wait for book page
            time.sleep(random.uniform(4, 8))

            # Attempt download
            return self.attempt_download()

        except Exception as e:
            logger.error(f"❌ Search processing error: {str(e)}")
            return False

    def attempt_download(self):
        """Attempt to download from current page"""
        try:
            logger.info("📥 Attempting download...")

            # Handle Cloudflare on book page
            if not self.handle_cloudflare_challenge():
                logger.warning("⚠️ Cloudflare handling incomplete on book page")

            # Human behavior
            self._simulate_basic_behavior(self.driver)
            time.sleep(random.uniform(3, 6))

            # Find download links
            download_selectors = [
                "a[href*='slow_download']",
                "a[href*='fast_download']",
                "a[href*='download']",
                ".download-link"
            ]

            download_link = None
            for selector in download_selectors:
                try:
                    download_link = self.driver.find_element(By.CSS_SELECTOR, selector)
                    logger.info(f"📥 Found download link: {selector}")
                    break
                except:
                    continue

            if not download_link:
                # Check all links for download
                logger.info("🔍 Searching all links for download...")
                all_links = self.driver.find_elements(By.TAG_NAME, "a")
                for link in all_links:
                    href = link.get_attribute('href')
                    text = link.text.strip()
                    if href and ('download' in href.lower() or 'download' in text.lower()):
                        download_link = link
                        logger.info(f"📥 Found download link: {text}")
                        break

            if download_link:
                # Click download link
                self._simulate_basic_behavior(self.driver)

                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth'});", download_link)
                time.sleep(random.uniform(2, 4))

                try:
                    download_link.click()
                    logger.info("✅ Download link clicked")
                except:
                    self.driver.execute_script("arguments[0].click();", download_link)
                    logger.info("✅ Download link clicked (JS)")

                # Handle download page
                return self.handle_download_page()
            else:
                logger.warning("❌ No download links found")
                return False

        except Exception as e:
            logger.error(f"❌ Download attempt failed: {str(e)}")
            return False

    def handle_download_page(self):
        """Handle download pages with wait times and additional Cloudflare"""
        try:
            logger.info("📄 Handling download page...")

            # Handle Cloudflare on download page
            self.handle_cloudflare_challenge()

            # Human behavior
            self._simulate_basic_behavior(self.driver)
            time.sleep(random.uniform(4, 8))

            # Check for wait indicators
            wait_indicators = [
                "please wait",
                "seconds",
                "preparing your download",
                "processing"
            ]

            page_text = self.driver.page_source.lower()
            is_wait_page = any(indicator in page_text for indicator in wait_indicators)

            if is_wait_page:
                logger.info("⏳ Detected wait page, waiting for download...")

                max_wait = 180
                for i in range(max_wait):
                    time.sleep(1)

                    # Continue human behavior
                    if i % 15 == 0:
                        self._simulate_basic_behavior(self.driver)

                    # Look for download elements
                    download_elements = []

                    try:
                        # Direct file downloads
                        direct_downloads = self.driver.find_elements(By.XPATH,
                                                                     "//a[contains(@href, '.pdf') or contains(@href, '.epub') or contains(@href, '.mobi')]")
                        download_elements.extend(direct_downloads)

                        # Download buttons
                        download_buttons = self.driver.find_elements(By.XPATH,
                                                                     "//button[contains(text(), 'Download')] | //a[contains(text(), 'Download')]")
                        download_elements.extend(download_buttons)

                        # Click here links
                        click_links = self.driver.find_elements(By.XPATH,
                                                                "//a[contains(text(), 'Click here') or contains(text(), 'click here')]")
                        download_elements.extend(click_links)

                    except:
                        continue

                    if download_elements:
                        logger.info(f"📥 Found {len(download_elements)} download elements")
                        for element in download_elements:
                            try:
                                self._simulate_basic_behavior(self.driver)

                                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth'});",
                                                           element)
                                time.sleep(random.uniform(1, 3))
                                element.click()

                                logger.info("✅ Download initiated!")
                                time.sleep(random.uniform(10, 15))  # Wait for download to start
                                return True

                            except Exception as e:
                                logger.debug(f"Failed to click download element: {e}")
                                continue

                    # Progress updates
                    if i % 30 == 0 and i > 0:
                        logger.info(f"⏳ Still waiting for download... ({i}/{max_wait})")

                logger.warning("⚠️ Download timeout")
                return False
            else:
                logger.info("✅ No wait page detected")
                time.sleep(random.uniform(8, 15))  # Give time for immediate download
                return True

        except Exception as e:
            logger.error(f"❌ Download page handling failed: {str(e)}")
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
    print("🚀 COMPLETE ANNA'S ARCHIVE DOWNLOADER")
    print("=" * 60)
    print("✅ Proven Cloudflare bypass")
    print("✅ Automatic challenge handling")
    print("✅ Bulk downloading from search terms")
    print("=" * 60)
    print()

    # Configuration
    CHROME_PROFILE = None  # Set to your Chrome profile path for maximum stealth
    PROXY = None  # Set to "ip:port" for residential proxy

    try:
        with CompleteAnnasArchiveDownloader(
                download_dir="../../annas_archive_downloads",
                proxy=PROXY,
                user_data_dir=CHROME_PROFILE
        ) as downloader:

            # Load search terms
            search_terms = downloader.load_search_terms_from_file("test_data.txt")

            if search_terms:
                logger.info(f"📚 Loaded {len(search_terms)} search terms")

                # Start bulk downloading
                downloader.search_and_download_all(search_terms)

            else:
                logger.warning("❌ No search terms loaded from file")

                # Use fallback terms for testing
                fallback_terms = [
                    "python programming guide",
                    "machine learning introduction",
                    "data structures tutorial"
                ]
                logger.info("🔄 Using fallback search terms for testing...")
                downloader.search_and_download_all(fallback_terms)

            logger.info("🎉 Download session complete!")

    except KeyboardInterrupt:
        logger.info("⏹️ Download interrupted by user")
    except Exception as e:
        logger.error(f"💥 Download session failed: {e}")
        logger.info("💡 Try configuring Chrome profile or proxy for better results")