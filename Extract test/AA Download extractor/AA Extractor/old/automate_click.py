#!/usr/bin/env python3
"""
Anna's Archive Downloader - GRID CLICK EVERYWHERE with Human-like Fallback
Systematically clicks all over the page to find the Cloudflare checkbox
Falls back to human-like movements when grid clicking is needed
"""

import os
import time
import random
import logging
import math
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

try:
    import pyautogui

    PYAUTOGUI_AVAILABLE = True
    # Configure pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    pyautogui.MINIMUM_DURATION = 0.1
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    print("❌ Install: pip install pyautogui")

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

        # Human behavior parameters (halved wait times)
        self.typing_speed_range = (0.025, 0.1)  # Was (0.05, 0.2)
        self.mouse_speed_range = (0.4, 1.0)  # Was (0.8, 2.0)
        self.pause_range = (0.5, 1.5)  # Was (1.0, 3.0)

        # Browser info for coordinate conversion
        self.browser_pos = None
        self.browser_size = None
        self._update_browser_info()

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

    def _update_browser_info(self):
        """Update browser position and size for coordinate conversion"""
        try:
            self.browser_pos = self.driver.get_window_position()
            self.browser_size = self.driver.get_window_size()
        except Exception as e:
            logger.warning(f"⚠️ Could not get browser info: {e}")
            self.browser_pos = {'x': 0, 'y': 0}
            self.browser_size = {'width': 1366, 'height': 768}

    def get_current_mouse_position(self):
        """Get current mouse cursor position"""
        if not PYAUTOGUI_AVAILABLE:
            logger.warning("⚠️ PyAutoGUI not available, using default position")
            return (400, 300)

        try:
            current_pos = pyautogui.position()
            logger.debug(f"🖱️ Current mouse position: {current_pos}")
            return current_pos
        except Exception as e:
            logger.warning(f"⚠️ Could not get mouse position: {e}")
            return (400, 300)

    def human_like_mouse_movement(self, start_pos, end_pos, duration=None):
        """Create human-like mouse movement with bezier curves"""
        if not PYAUTOGUI_AVAILABLE:
            logger.warning("⚠️ PyAutoGUI not available, skipping mouse movement")
            return False

        try:
            if duration is None:
                duration = random.uniform(0.4, 1.0)  # Halved from 0.8, 2.0

            start_x, start_y = start_pos
            end_x, end_y = end_pos

            # Calculate distance and adjust duration (halved)
            distance = math.sqrt((end_x - start_x) ** 2 + (end_y - start_y) ** 2)

            if distance > 300:
                duration *= 0.3  # Was 0.6
            elif distance < 50:
                duration *= 0.9  # Was 1.8

            logger.debug(f"🖱️ Moving mouse from {start_pos} to {end_pos} over {duration:.2f}s")

            # Create bezier curve control points
            control1_x = start_x + (end_x - start_x) * 0.25 + random.randint(-80, 80)
            control1_y = start_y + (end_y - start_y) * 0.25 + random.randint(-50, 50)

            control2_x = start_x + (end_x - start_x) * 0.75 + random.randint(-50, 50)
            control2_y = start_y + (end_y - start_y) * 0.75 + random.randint(-30, 30)

            # Generate smooth bezier curve points
            steps = max(20, int(duration * 60))
            points = []

            for i in range(steps + 1):
                t = i / steps

                # Cubic bezier curve calculation
                x = (1 - t) ** 3 * start_x + 3 * (1 - t) ** 2 * t * control1_x + 3 * (
                            1 - t) * t ** 2 * control2_x + t ** 3 * end_x
                y = (1 - t) ** 3 * start_y + 3 * (1 - t) ** 2 * t * control1_y + 3 * (
                            1 - t) * t ** 2 * control2_y + t ** 3 * end_y

                # Add natural hand tremor
                tremor_x = random.uniform(-0.8, 0.8)
                tremor_y = random.uniform(-0.8, 0.8)

                points.append((int(x + tremor_x), int(y + tremor_y)))

            # Execute smooth movement
            for i, point in enumerate(points):
                try:
                    pyautogui.moveTo(point[0], point[1])

                    # Variable speed
                    speed_factor = 1.0
                    if i < len(points) * 0.2 or i > len(points) * 0.8:
                        speed_factor = 1.5

                    time.sleep((duration / len(points)) * speed_factor)
                except Exception as e:
                    logger.debug(f"Movement point error: {e}")
                    continue

            logger.debug("✅ Human-like mouse movement completed")
            return True

        except Exception as e:
            logger.error(f"❌ Mouse movement failed: {e}")
            return False

    def convert_webpage_to_screen_coords(self, web_x, web_y):
        """Convert webpage coordinates to screen coordinates"""
        try:
            self._update_browser_info()

            # Account for browser chrome
            chrome_height = 120
            chrome_width = 8

            screen_x = self.browser_pos['x'] + web_x + chrome_width
            screen_y = self.browser_pos['y'] + web_y + chrome_height

            return (int(screen_x), int(screen_y))
        except Exception as e:
            logger.warning(f"⚠️ Coordinate conversion failed: {e}")
            return (int(web_x), int(web_y + 120))

    def human_like_click(self, coordinates):
        """Perform human-like click at screen coordinates"""
        try:
            logger.debug(f"🖱️ Performing human-like click at {coordinates}")

            current_pos = self.get_current_mouse_position()

            # Pre-click pause
            time.sleep(random.uniform(0.1, 0.3))

            # Move mouse to target
            movement_duration = random.uniform(0.3, 0.8)
            success = self.human_like_mouse_movement(current_pos, coordinates, movement_duration)

            if not success and PYAUTOGUI_AVAILABLE:
                pyautogui.moveTo(coordinates[0], coordinates[1], duration=0.2)

            # Hover pause
            time.sleep(random.uniform(0.05, 0.15))

            # Perform the click
            if PYAUTOGUI_AVAILABLE:
                click_duration = random.uniform(0.08, 0.18)
                pyautogui.mouseDown()
                time.sleep(click_duration)
                pyautogui.mouseUp()

                logger.debug("✅ Human-like click completed")

                # Post-click pause
                time.sleep(random.uniform(0.1, 0.3))
                return True
            else:
                logger.warning("❌ PyAutoGUI not available for clicking")
                return False

        except Exception as e:
            logger.error(f"❌ Human-like click failed: {e}")
            return False

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

                # Try human-like grid clicking approach
                success = self._click_everywhere_human_like()

                if success:
                    return self._wait_for_completion()
                else:
                    logger.warning("❌ Human-like grid clicking failed")
                    return False
            else:
                logger.info("✅ No Cloudflare challenge detected")
                return True

        except Exception as e:
            logger.error(f"❌ Grid click Cloudflare handling error: {e}")
            return False

    def _click_everywhere_human_like(self):
        """Direct human-like clicks at Cloudflare checkbox coordinates"""
        try:
            logger.info("🎯 DIRECT HUMAN-LIKE CLICKS at Cloudflare checkbox...")

            # Target coordinates to try
            targets = [
                (853, 260),
                (853, 270),
                (853, 280),
            ]

            # Mouse position monitoring in background
            import threading

            def monitor_mouse_position():
                """Monitor and print mouse position every 2 seconds"""
                while True:
                    try:
                        if PYAUTOGUI_AVAILABLE:
                            pos = pyautogui.position()
                            print(f"🖱️ MOUSE POSITION: {pos}")
                        time.sleep(2)
                    except:
                        break

            # Start mouse monitoring thread
            monitor_thread = threading.Thread(target=monitor_mouse_position, daemon=True)
            monitor_thread.start()

            for i, (target_web_x, target_web_y) in enumerate(targets, 1):
                logger.info(f"🎯 Target {i}/2: ({target_web_x}, {target_web_y})")

                # Convert webpage coordinates to screen coordinates
                screen_coords = self.convert_webpage_to_screen_coords(target_web_x, target_web_y)
                logger.info(f"🖥️ Screen coordinates: {screen_coords}")

                # Get current mouse position
                current_pos = self.get_current_mouse_position()
                logger.info(f"📍 Current position: {current_pos}")

                # Reduced human reading/decision time (halved)
                decision_time = random.uniform(0.75, 1.5)  # Was 1.5-3.0
                logger.info(f"🤔 Decision time: {decision_time:.1f}s")
                time.sleep(decision_time)

                # Perform human-like movement and click
                logger.info(f"🖱️ Moving to target {i}...")

                # Create natural movement duration (halved)
                distance = math.sqrt(
                    (screen_coords[0] - current_pos[0]) ** 2 + (screen_coords[1] - current_pos[1]) ** 2)
                movement_duration = min(1.25, max(0.4, distance / 800))  # Was min(2.5, max(0.8, distance/400))

                logger.info(f"⏱️ Movement duration: {movement_duration:.1f}s (distance: {distance:.0f}px)")

                # Execute human-like movement
                success = self.human_like_mouse_movement(current_pos, screen_coords, movement_duration)

                if not success and PYAUTOGUI_AVAILABLE:
                    logger.warning("⚠️ Bezier movement failed, using direct movement")
                    pyautogui.moveTo(screen_coords[0], screen_coords[1], duration=movement_duration)

                # Brief pause at target (halved)
                hover_time = random.uniform(0.15, 0.4)  # Was 0.3-0.8
                logger.info(f"⏸️ Hovering for {hover_time:.1f}s")
                time.sleep(hover_time)

                # Perform the click
                logger.info(f"🖱️ Clicking target {i}...")
                if PYAUTOGUI_AVAILABLE:
                    # Human-like click with realistic timing (halved)
                    click_duration = random.uniform(0.05, 0.1)  # Was 0.1-0.2
                    pyautogui.mouseDown()
                    time.sleep(click_duration)
                    pyautogui.mouseUp()

                    logger.info(f"✅ Click {i} completed at ({target_web_x}, {target_web_y})")

                    # Post-click pause (halved)
                    reaction_time = random.uniform(0.25, 0.6)  # Was 0.5-1.2
                    logger.info(f"⏳ Reaction time: {reaction_time:.1f}s")
                    time.sleep(reaction_time)

                    # Check if challenge is resolved after each click
                    try:
                        current_page_text = self.driver.page_source.lower()
                        challenge_indicators = [
                            "verify you are human",
                            "checking your browser",
                            "security check"
                        ]

                        challenge_still_present = any(
                            indicator in current_page_text for indicator in challenge_indicators)

                        if not challenge_still_present:
                            logger.info(f"🎉 SUCCESS! Click {i} at ({target_web_x}, {target_web_y}) resolved challenge!")
                            return True
                    except Exception as e:
                        logger.debug(f"Challenge check error: {e}")

                    # Short delay before next target (halved)
                    if i < len(targets):
                        inter_target_delay = random.uniform(0.5, 1.0)  # Was 1.0-2.0
                        logger.info(f"⏳ Delay before next target: {inter_target_delay:.1f}s")
                        time.sleep(inter_target_delay)

                else:
                    logger.error("❌ PyAutoGUI not available for physical clicking")
                    return False

            logger.info("✅ All target clicks completed")
            return True

        except Exception as e:
            logger.error(f"❌ Direct human-like clicks failed: {e}")
            return False

    def _click_at_coordinates(self, x, y):
        """Click at specific coordinates using multiple methods (LEGACY - kept for compatibility)"""
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

    def simulate_human_typing(self, element, text):
        """Type text with human-like timing variations (halved speeds)"""
        try:
            element.clear()
            time.sleep(random.uniform(0.15, 0.35))  # Was 0.3-0.7

            for i, char in enumerate(text):
                element.send_keys(char)

                # Variable typing speed (halved)
                if char == ' ':
                    time.sleep(random.uniform(0.075, 0.2))  # Was 0.15-0.4
                elif char in '.,!?;:':
                    time.sleep(random.uniform(0.125, 0.25))  # Was 0.25-0.5
                else:
                    time.sleep(random.uniform(0.025, 0.1))  # Was 0.05-0.2

            logger.info(f"✅ Human-like typing completed")
            return True

        except Exception as e:
            logger.error(f"❌ Human-like typing failed: {e}")
            return False

    def _wait_for_completion(self):
        """Wait for challenge completion"""
        try:
            logger.info("⏳ Waiting for challenge completion...")

            max_wait = 30
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

            # Delay between searches (halved)
            if i < len(search_terms):
                delay = random.uniform(4, 7.5)  # Was 8-15
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

            # Perform search with human-like typing
            search_box.clear()
            time.sleep(1)

            # Type search term with human-like behavior
            success = self.simulate_human_typing(search_box, search_term)
            if not success:
                # Fallback to regular typing
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
    print("🚀 GRID CLICK EVERYWHERE DOWNLOADER with HUMAN-LIKE FALLBACK")
    print("=" * 70)
    print("🎯 Systematically clicks everywhere to find Cloudflare checkbox")
    print("🤖 Uses human-like mouse movements when grid clicking is needed")
    print("🔲 Grid pattern: Every 25 pixels across the page")
    print("🎲 Random pattern: Random coordinates across viewport")
    print("🌀 Spiral pattern: Spiral outward from center")
    print("🖱️ Human-like: Bezier curves, natural timing, real mouse control")
    print("=" * 70)
    print()

    if not PYAUTOGUI_AVAILABLE:
        print("⚠️ WARNING: PyAutoGUI not available")
        print("   Install with: pip install pyautogui")
        print("   Human-like movements will be disabled")
        print()

    # Configuration
    PROXY = None  # Set to "ip:port" for proxy
    CLICK_METHOD = "grid"  # Options: "grid", "random", "spiral"

    print(f"🎯 Using {CLICK_METHOD.upper()} clicking method with human-like enhancements")
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

            logger.info("🎉 Enhanced grid click session complete!")

    except KeyboardInterrupt:
        logger.info("⏹️ Session interrupted")
    except Exception as e:
        logger.error(f"💥 Session failed: {e}")
        print(f"\n💡 Requirements:")
        print("   pip install undetected-chromedriver")
        print("   pip install pyautogui (for human-like movements)")
        print("   pip install selenium")
        print(f"\n🎯 Try different click methods:")
        print("   CLICK_METHOD = 'grid'   # Systematic grid with human-like movements")
        print("   CLICK_METHOD = 'random' # Random clicking")
        print("   CLICK_METHOD = 'spiral' # Spiral pattern")