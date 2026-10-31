#!/usr/bin/env python3
"""
Anna's Archive Downloader - GRID CLICK EVERYWHERE
Systematically clicks all over the page to find the Cloudflare checkbox
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
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException

try:
    import undetected_chromedriver as uc

    UNDETECTED_AVAILABLE = True
except ImportError:
    UNDETECTED_AVAILABLE = False
    print("❌ Install: pip install undetected-chromedriver")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class GridClickDownloader:
    def __init__(self, download_dir="downloads", wait_time=30, proxy=None):
        """
        Anna's Archive downloader that clicks EVERYWHERE to find Cloudflare checkbox
        """
        self.base_url = "https://annas-archive.org"
        self.download_dir = download_dir
        self.wait_time = wait_time
        self.proxy = proxy

        os.makedirs(download_dir, exist_ok=True)

        # Setup browser
        self.driver = self._setup_chrome()
        self.wait = WebDriverWait(self.driver, wait_time)
        self.actions = ActionChains(self.driver)

    def _setup_chrome(self):
        """Setup Chrome with working configuration"""
        logger.info("🚀 Setting up Chrome...")

        if not UNDETECTED_AVAILABLE:
            raise ImportError("undetected-chromedriver required")

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

            # Apply stealth
            self._apply_stealth(driver)

            logger.info("✅ Chrome setup complete!")
            return driver

        except Exception as e:
            logger.error(f"❌ Chrome setup failed: {e}")
            raise

    def _apply_stealth(self, driver):
        """Apply stealth measures"""
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
            logger.info("✅ Stealth applied")

        except Exception as e:
            logger.warning(f"⚠️ Stealth application failed: {e}")

    def handle_cloudflare_grid_click(self):
        """Handle Cloudflare by clicking EVERYWHERE in a grid pattern"""
        try:
            logger.info("🔍 Checking for Cloudflare challenges...")

            time.sleep(3)  # Let page stabilize

            page_text = self.driver.page_source.lower()
            cloudflare_indicators = [
                "verify you are human",
                "checking your browser",
                "security check",
                "cloudflare",
                "challenge-form",
                "turnstile"
            ]

            is_cloudflare = any(indicator in page_text for indicator in cloudflare_indicators)

            if is_cloudflare:
                logger.info("🚨 Cloudflare challenge detected!")
                logger.info("🎯 Starting GRID CLICK EVERYWHERE approach...")

                # Simulate human behavior first
                self._simulate_human_behavior()

                # Try grid clicking approach
                success = self._click_everywhere_grid()

                if success:
                    return self._wait_for_completion()
                else:
                    logger.warning("❌ Grid clicking failed")
                    return False
            else:
                logger.info("✅ No Cloudflare challenge detected")
                return True

        except Exception as e:
            logger.error(f"❌ Grid click Cloudflare handling error: {e}")
            return False

    def _click_everywhere_grid(self):
        """Click everywhere in a systematic grid pattern"""
        try:
            logger.info("🎯 CLICKING EVERYWHERE IN GRID PATTERN...")

            # Get viewport dimensions
            viewport_width = self.driver.execute_script("return window.innerWidth")
            viewport_height = self.driver.execute_script("return window.innerHeight")

            logger.info(f"📐 Viewport: {viewport_width}x{viewport_height}")

            # Grid parameters - click every 25 pixels
            grid_size = 25
            click_count = 0
            max_clicks = 500  # Safety limit

            # Store initial page state
            initial_page_text = self.driver.page_source.lower()

            # Systematic grid clicking
            for y in range(50, min(viewport_height - 50, 600), grid_size):
                for x in range(50, min(viewport_width - 50, 1000), grid_size):
                    if click_count >= max_clicks:
                        logger.warning(f"🛑 Reached maximum clicks ({max_clicks})")
                        break

                    try:
                        click_count += 1

                        # Log progress every 20 clicks
                        if click_count % 20 == 0:
                            logger.info(f"🎯 Grid click {click_count}: ({x}, {y})")

                        # Perform click at coordinates
                        self._click_at_coordinates(x, y)

                        # Quick check if challenge is resolved (every 5 clicks)
                        if click_count % 5 == 0:
                            current_page_text = self.driver.page_source.lower()
                            challenge_indicators = [
                                "verify you are human",
                                "checking your browser",
                                "security check"
                            ]

                            challenge_still_present = any(
                                indicator in current_page_text for indicator in challenge_indicators)

                            if not challenge_still_present:
                                logger.info(f"🎉 SUCCESS! Grid click {click_count} at ({x}, {y}) resolved challenge!")
                                return True

                        # Small delay between clicks
                        time.sleep(0.1)

                    except Exception as e:
                        logger.debug(f"Grid click at ({x}, {y}) failed: {e}")
                        continue

                # Break outer loop if max clicks reached
                if click_count >= max_clicks:
                    break

            logger.info(f"🎯 Grid clicking complete. Total clicks: {click_count}")

            # Final check
            final_page_text = self.driver.page_source.lower()
            challenge_indicators = ["verify you are human", "checking your browser", "security check"]
            challenge_still_present = any(indicator in final_page_text for indicator in challenge_indicators)

            if not challenge_still_present:
                logger.info("🎉 Challenge resolved by grid clicking!")
                return True
            else:
                logger.warning("❌ Grid clicking did not resolve challenge")
                return False

        except Exception as e:
            logger.error(f"❌ Grid clicking error: {e}")
            return False

    def _click_at_coordinates(self, x, y):
        """Click at specific coordinates using multiple methods"""
        try:
            # Method 1: ActionChains click
            try:
                self.actions.move_by_offset(x, y).click().perform()
                self.actions.reset_actions()
                return True
            except:
                pass

            # Method 2: JavaScript click at coordinates
            try:
                self.driver.execute_script(f"""
                    var element = document.elementFromPoint({x}, {y});
                    if (element) {{
                        var event = new MouseEvent('click', {{
                            clientX: {x},
                            clientY: {y},
                            bubbles: true,
                            cancelable: true
                        }});
                        element.dispatchEvent(event);
                    }}
                """)
                return True
            except:
                pass

            # Method 3: Direct coordinate click
            try:
                self.driver.execute_script(f"""
                    var event = new MouseEvent('click', {{
                        clientX: {x},
                        clientY: {y},
                        bubbles: true,
                        cancelable: true,
                        view: window
                    }});
                    document.dispatchEvent(event);
                """)
                return True
            except:
                pass

            return False

        except Exception as e:
            logger.debug(f"Click at ({x}, {y}) failed: {e}")
            return False

    def _click_everywhere_random(self):
        """Alternative: Random clicking everywhere"""
        try:
            logger.info("🎲 RANDOM CLICKING EVERYWHERE...")

            # Get viewport dimensions
            viewport_width = self.driver.execute_script("return window.innerWidth")
            viewport_height = self.driver.execute_script("return window.innerHeight")

            click_count = 0
            max_clicks = 200

            for _ in range(max_clicks):
                click_count += 1

                # Random coordinates
                x = random.randint(50, min(viewport_width - 50, 1000))
                y = random.randint(50, min(viewport_height - 50, 600))

                if click_count % 10 == 0:
                    logger.info(f"🎲 Random click {click_count}: ({x}, {y})")

                # Click at random coordinates
                self._click_at_coordinates(x, y)

                # Check if challenge resolved (every 3 clicks)
                if click_count % 3 == 0:
                    current_page_text = self.driver.page_source.lower()
                    if "verify you are human" not in current_page_text:
                        logger.info(f"🎉 SUCCESS! Random click {click_count} at ({x}, {y}) resolved challenge!")
                        return True

                time.sleep(0.05)

            logger.info(f"🎲 Random clicking complete. Total clicks: {click_count}")

            # Final check
            final_page_text = self.driver.page_source.lower()
            if "verify you are human" not in final_page_text:
                logger.info("🎉 Challenge resolved by random clicking!")
                return True
            else:
                logger.warning("❌ Random clicking did not resolve challenge")
                return False

        except Exception as e:
            logger.error(f"❌ Random clicking error: {e}")
            return False

    def _click_everywhere_spiral(self):
        """Alternative: Spiral clicking pattern"""
        try:
            logger.info("🌀 SPIRAL CLICKING PATTERN...")

            # Start from center and spiral outward
            center_x = 400
            center_y = 300
            radius = 10
            angle = 0
            click_count = 0
            max_clicks = 300

            while radius < 300 and click_count < max_clicks:
                # Calculate spiral coordinates
                x = int(center_x + radius * random.uniform(0.8, 1.2) * (1 if angle % 180 < 90 else -1))
                y = int(center_y + radius * random.uniform(0.8, 1.2) * (1 if angle % 360 < 180 else -1))

                # Keep within reasonable bounds
                x = max(50, min(x, 1000))
                y = max(50, min(y, 600))

                click_count += 1

                if click_count % 15 == 0:
                    logger.info(f"🌀 Spiral click {click_count}: ({x}, {y}) radius={radius}")

                # Click at spiral coordinates
                self._click_at_coordinates(x, y)

                # Check if challenge resolved
                if click_count % 4 == 0:
                    current_page_text = self.driver.page_source.lower()
                    if "verify you are human" not in current_page_text:
                        logger.info(f"🎉 SUCCESS! Spiral click {click_count} at ({x}, {y}) resolved challenge!")
                        return True

                # Advance spiral
                angle += 30
                if angle % 360 == 0:
                    radius += 15

                time.sleep(0.08)

            logger.info(f"🌀 Spiral clicking complete. Total clicks: {click_count}")

            # Final check
            final_page_text = self.driver.page_source.lower()
            if "verify you are human" not in final_page_text:
                logger.info("🎉 Challenge resolved by spiral clicking!")
                return True
            else:
                logger.warning("❌ Spiral clicking did not resolve challenge")
                return False

        except Exception as e:
            logger.error(f"❌ Spiral clicking error: {e}")
            return False

    def _simulate_human_behavior(self):
        """Simulate human behavior before clicking everywhere"""
        try:
            logger.info("🤖 Simulating human behavior...")

            # Reading pause
            time.sleep(random.uniform(2, 4))

            # Mouse movements
            for _ in range(3):
                x = random.randint(200, 800)
                y = random.randint(200, 500)
                self.driver.execute_script(f"""
                    var event = new MouseEvent('mousemove', {{
                        clientX: {x},
                        clientY: {y},
                        bubbles: true
                    }});
                    document.dispatchEvent(event);
                """)
                time.sleep(random.uniform(0.3, 0.8))

            # Small scroll
            scroll_amount = random.randint(50, 150)
            self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            time.sleep(random.uniform(1, 2))

            logger.info("✅ Human behavior simulation complete")

        except Exception as e:
            logger.debug(f"Human behavior simulation error: {e}")

    def _wait_for_completion(self):
        """Wait for challenge completion"""
        try:
            logger.info("⏳ Waiting for challenge completion...")

            max_wait = 30  # Reduced since we already found success
            initial_url = self.driver.current_url

            for i in range(max_wait):
                time.sleep(1)

                # Check completion
                try:
                    current_url = self.driver.current_url
                    page_text = self.driver.page_source.lower()

                    challenge_indicators = [
                        "verify you are human",
                        "checking your browser",
                        "security check"
                    ]

                    still_challenging = any(indicator in page_text for indicator in challenge_indicators)

                    if not still_challenging or current_url != initial_url:
                        logger.info("✅ Challenge completion confirmed!")
                        time.sleep(random.uniform(1, 3))
                        return True

                    # Check for success elements
                    success_elements = self.driver.find_elements(By.CSS_SELECTOR,
                                                                 "input[placeholder*='search'], input[type='search']")
                    if success_elements:
                        logger.info("✅ Search elements found - challenge completed!")
                        return True

                except Exception as e:
                    logger.debug(f"Completion check error: {e}")

                if i % 10 == 0 and i > 0:
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

    def search_and_download_all(self, search_terms, click_method="grid"):
        """Main downloading method with grid clicking"""
        if not search_terms:
            logger.warning("⚠️ No search terms provided")
            return

        successful_downloads = []
        failed_downloads = []

        logger.info(f"🚀 Starting downloads with {click_method.upper()} CLICKING...")

        for i, term in enumerate(search_terms, 1):
            logger.info(f"\n{'=' * 60}")
            logger.info(f"🔍 Processing {i}/{len(search_terms)}: '{term}'")
            logger.info(f"{'=' * 60}")

            try:
                if self.process_single_search(term, click_method):
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
        logger.info(f"📊 GRID CLICK DOWNLOAD SUMMARY")
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

    def process_single_search(self, search_term, click_method="grid"):
        """Process single search with grid clicking"""
        try:
            logger.info(f"🌐 Navigating to Anna's Archive...")

            # Navigate to site
            self.driver.get(self.base_url)

            # Handle Cloudflare with grid clicking
            if click_method == "grid":
                success = self.handle_cloudflare_grid_click()
            elif click_method == "random":
                success = self._click_everywhere_random()
            elif click_method == "spiral":
                success = self._click_everywhere_spiral()
            else:
                success = self.handle_cloudflare_grid_click()

            if not success:
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
            if click_method == "grid":
                self.handle_cloudflare_grid_click()
            elif click_method == "random":
                self._click_everywhere_random()
            elif click_method == "spiral":
                self._click_everywhere_spiral()

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
            return self.attempt_download(click_method)

        except Exception as e:
            logger.error(f"❌ Search processing error: {str(e)}")
            return False

    def attempt_download(self, click_method="grid"):
        """Attempt download with grid clicking"""
        try:
            logger.info("📥 Attempting download...")

            # Handle Cloudflare on book page
            if click_method == "grid":
                success = self.handle_cloudflare_grid_click()
            elif click_method == "random":
                success = self._click_everywhere_random()
            elif click_method == "spiral":
                success = self._click_everywhere_spiral()

            if not success:
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
                time.sleep(1)

                try:
                    download_link.click()
                except:
                    self.driver.execute_script("arguments[0].click();", download_link)

                # Handle download page
                return self.handle_download_page(click_method)
            else:
                logger.warning("❌ No download links found")
                return False

        except Exception as e:
            logger.error(f"❌ Download attempt failed: {str(e)}")
            return False

    def handle_download_page(self, click_method="grid"):
        """Handle download page with grid clicking"""
        try:
            logger.info("📄 Handling download page...")

            # Handle Cloudflare on download page
            if click_method == "grid":
                self.handle_cloudflare_grid_click()
            elif click_method == "random":
                self._click_everywhere_random()
            elif click_method == "spiral":
                self._click_everywhere_spiral()

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
                                    time.sleep(10)
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
                time.sleep(10)
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
    print("🚀 GRID CLICK EVERYWHERE DOWNLOADER")
    print("=" * 60)
    print("🎯 Systematically clicks everywhere to find Cloudflare checkbox")
    print("🔲 Grid pattern: Every 25 pixels across the page")
    print("🎲 Random pattern: Random coordinates across viewport")
    print("🌀 Spiral pattern: Spiral outward from center")
    print("=" * 60)
    print()

    # Configuration
    PROXY = None  # Set to "ip:port" for proxy
    CLICK_METHOD = "grid"  # Options: "grid", "random", "spiral"

    print(f"🎯 Using {CLICK_METHOD.upper()} clicking method")
    print()

    try:
        with GridClickDownloader(
                download_dir="../../annas_archive_downloads",
                proxy=PROXY
        ) as downloader:

            # Load search terms
            search_terms = downloader.load_search_terms_from_file("test_data.txt")

            if search_terms:
                logger.info(f"📚 Starting download with {CLICK_METHOD} clicking...")
                downloader.search_and_download_all(search_terms, CLICK_METHOD)
            else:
                logger.warning("❌ No search terms found")
                fallback_terms = ["Manufacturing Consent Noam Chomsky"]
                logger.info("🔄 Using fallback term...")
                downloader.search_and_download_all(fallback_terms, CLICK_METHOD)

            logger.info("🎉 Grid click session complete!")

    except KeyboardInterrupt:
        logger.info("⏹️ Session interrupted")
    except Exception as e:
        logger.error(f"💥 Session failed: {e}")
        print(f"\n💡 Try different click methods:")
        print("   CLICK_METHOD = 'grid'   # Systematic grid")
        print("   CLICK_METHOD = 'random' # Random clicking")
        print("   CLICK_METHOD = 'spiral' # Spiral pattern")