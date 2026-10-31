
import os
import time
import json
import logging
import requests
import difflib
import random
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urljoin, urlparse
from bs4 import BeautifulSoup

try:
    from tqdm import tqdm
except ImportError:
    # Fallback if tqdm not installed
    def tqdm(iterable, **kwargs):
        print(f"Processing {len(iterable) if hasattr(iterable, '__len__') else 'items'} items...")
        return iterable

# --- CONFIGURATION ---
DOWNLOAD_DIR = "downloads"
HISTORY_FILE = "download_history.json"
MAX_WORKERS = 2  # Reduced to avoid spawning too many browsers with Playwright
CONNECTION_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 120
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("downloader.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- UTILS ---

def clean_filename(title):
    return "".join([c for c in title if c.isalnum() or c in (' ', '-', '_', '.')]).strip().replace(" ", "_")

def check_title_similarity(query_title, found_title):
    t1 = query_title.lower()
    t2 = found_title.lower()
    ratio = difflib.SequenceMatcher(None, t1, t2).ratio()
    if ratio < 0.4 and (t1 in t2 or t2 in t1):
        return 0.8
    return ratio

def download_file(url, filepath):
    try:
        if os.path.exists(filepath):
            logger.info(f"File exists: {filepath}")
            return True
            
        logger.info(f"Downloading {url} -> {filepath}")
        response = requests.get(url, headers=HEADERS, stream=True, timeout=DOWNLOAD_TIMEOUT)
        response.raise_for_status()
        
        # Basic content type check
        ct = response.headers.get('Content-Type', '').lower()
        if 'text/html' in ct:
            logger.warning(f"Skipping {url}: URL returned HTML instead of binary.")
            return False

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=16384):
                f.write(chunk)
                
        if os.path.getsize(filepath) < 2000: # <2KB
            logger.warning(f"File too small ({os.path.getsize(filepath)} bytes), deleting: {filepath}")
            os.remove(filepath)
            return False
            
        return True
    except Exception as e:
        logger.error(f"Download failed for {url}: {e}")
        if os.path.exists(filepath):
            os.remove(filepath)
        return False

# --- PROVIDERS ---

class Provider:
    def __init__(self):
        self.name = "Generic"
    
    def search_and_download(self, query, safe_name):
        """Returns (success_bool, download_url_or_none)"""
        raise NotImplementedError

class AnnasArchiveProvider(Provider):
    def __init__(self):
        self.name = "Anna's Archive (Playwright)"
        self.search_url = "https://annas-archive.se/search"
    
    def search_and_download(self, query, safe_name):
        # 1. Search (requests is fine for the search page usually, unless strictly blocked)
        # However, to be consistent and avoid blocks, we'll try requests first for speed, 
        # but the download part DEFINITELY needs playwright.
        
        candidates = []
        try:
            url = f"{self.search_url}?q={quote(query)}"
            r = requests.get(url, headers=HEADERS, timeout=CONNECTION_TIMEOUT)
            
            if r.status_code == 200:
                soup = BeautifulSoup(r.content, "html.parser")
                for a in soup.find_all("a"):
                    href = a.get("href", "")
                    if "/md5/" in href:
                        text = a.get_text(strip=True)
                        score = check_title_similarity(query, text)
                        if score > 0.4:
                            candidates.append((score, urljoin(url, href)))
                candidates.sort(key=lambda x: x[0], reverse=True)
            else:
                logger.warning(f"AA Search blocked (Status {r.status_code}), might need full browser search later.")
        except Exception as e:
            logger.error(f"AA Search Error: {e}")

        # 2. Try to download top candidates using Playwright
        if candidates:
            from playwright.sync_api import sync_playwright
            
            with sync_playwright() as p:
                # Launch browser with anti-detection args
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                ) 
                
                # Create a context with realistic headers and screen size
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={'width': 1920, 'height': 1080},
                    locale="en-US",
                    timezone_id="America/Chicago" # Match user rough location
                )
                
                # Add init script to remove webdriver property
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)
                
                page = context.new_page()
                
                for score, item_url in candidates[:2]: # Only try top 2
                    # Random delay to assume human behavior and avoid 429
                    time.sleep(random.uniform(10, 20))
                    
                    logger.info(f"Checking AA candidate via Playwright: {item_url}")
                    dl_link = self.resolve_download_link_playwright(page, item_url)
                    
                    if dl_link:
                        logger.info(f"Found final download link: {dl_link}")
                        filename = f"{safe_name}_annas.pdf"
                        filepath = os.path.join(DOWNLOAD_DIR, filename)
                        
                        cookies = {c['name']: c['value'] for c in context.cookies()}
                        
                        if self.download_with_cookies(dl_link, filepath, cookies):
                             browser.close()
                             return True, filename
                
                browser.close()
                
        return False, None

    def resolve_download_link_playwright(self, page, item_url):
        try:
            page.goto(item_url, timeout=60000, wait_until="domcontentloaded")
            
            # Find the "slow partner" link. 
            links = page.locator("a").all()
            target_link = None
            
            for link in links:
                href = link.get_attribute("href")
                if href and "/slow_download/" in href:
                    target_link = href
                    break
            
            if not target_link:
                return None
                
            full_target = urljoin(item_url, target_link)
            logger.info(f"  Following Slow Partner link: {full_target}")
            
            # Navigate to the wait page
            page.goto(full_target, timeout=60000, wait_until="domcontentloaded")
            
            logger.info("  Waiting for countdown (approx 30s)...")
            
            try:
                # Wait for the download link
                # Using a broad selector for 'Download now'
                download_locator = page.locator("a", has_text="Download now")
                download_locator.wait_for(state="visible", timeout=45000)
                
                final_href = download_locator.get_attribute("href")
                return urljoin(full_target, final_href)
            except Exception as e:
                logger.warning(f"  Timeout waiting for download button. Taking screenshot.")
                timestamp = int(time.time())
                page.screenshot(path=f"debug_aa_timeout_{timestamp}.png")
                return None
                
        except Exception as e:
            logger.error(f"  Playwright navigation error: {e}")
            return None
            
    def download_with_cookies(self, url, filepath, cookies):
        retries = 3
        for attempt in range(retries):
            try:
                 # Streaming download with requests + cookies
                 r = requests.get(url, headers=HEADERS, cookies=cookies, stream=True, timeout=DOWNLOAD_TIMEOUT)
                 
                 if r.status_code == 429:
                     wait_time = (attempt + 1) * 10 + random.uniform(1, 5)
                     logger.warning(f"  Rate limited (429). Waiting {wait_time:.1f}s before retry {attempt+1}/{retries}...")
                     time.sleep(wait_time)
                     continue
                     
                 r.raise_for_status()
                 
                 with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=16384):
                        f.write(chunk)
                        
                 # Better validation: check if file is at least 50KB
                 file_size = os.path.getsize(filepath)
                 if file_size < 50000:  # Less than 50KB is likely an error page
                    logger.warning(f"  File too small ({file_size} bytes), likely not a valid book")
                    os.remove(filepath)
                    return False
                 
                 logger.info(f"  Downloaded successfully ({file_size / 1024 / 1024:.2f} MB)")
                 return True
            except Exception as e:
                logger.error(f"  Download failed: {e}")
                if os.path.exists(filepath):
                    os.remove(filepath)
                if attempt < retries - 1:
                    time.sleep(5)
                else:
                    return False
        return False

class OpenAlexProvider(Provider):
    def __init__(self):
        self.name = "OpenAlex"
        self.api_url = "https://api.openalex.org/works"

    def search_and_download(self, query, safe_name):
        try:
            params = {"search": query, "per-page": 1}
            r = requests.get(self.api_url, params=params, headers=HEADERS, timeout=CONNECTION_TIMEOUT)
            if r.status_code != 200: return False, None
            
            results = r.json().get("results", [])
            if not results: return False, None
            
            work = results[0]
            # Try best OA location
            locations = [work.get("best_oa_location")] + work.get("locations", [])
            
            for loc in locations:
                if not loc: continue
                pdf_url = loc.get("pdf_url")
                if pdf_url:
                    filename = f"{safe_name}_openalex.pdf"
                    filepath = os.path.join(DOWNLOAD_DIR, filename)
                    if download_file(pdf_url, filepath):
                        return True, filename
        except Exception as e:
            logger.error(f"OpenAlex Error: {e}")
        return False, None

class InternetArchiveProvider(Provider):
    def __init__(self):
        self.name = "Internet Archive"
        self.search_url = "https://archive.org/advancedsearch.php"

    def search_and_download(self, query, safe_name):
        try:
            q = f'({query}) AND mediatype:(texts)'
            params = {
                "q": q,
                "fl[]": ["identifier", "title", "format"],
                "rows": 3,
                "output": "json"
            }
            r = requests.get(self.search_url, params=params, headers=HEADERS, timeout=CONNECTION_TIMEOUT)
            docs = r.json().get("response", {}).get("docs", [])
            
            for d in docs:
                title = d.get("title", "")
                if check_title_similarity(query, title) < 0.4:
                    continue
                
                ident = d.get("identifier")
                # Get metadata to find PDF
                meta_url = f"https://archive.org/metadata/{ident}"
                mr = requests.get(meta_url, headers=HEADERS, timeout=CONNECTION_TIMEOUT)
                files = mr.json().get("files", [])
                
                for f in files:
                    if f.get("format") == "Portable Document Format" or f.get("name", "").lower().endswith(".pdf"):
                        fname = f.get("name")
                        dl_link = f"https://archive.org/download/{ident}/{fname}"
                        filename = f"{safe_name}_ia.pdf"
                        filepath = os.path.join(DOWNLOAD_DIR, filename)
                        if download_file(dl_link, filepath):
                            return True, filename
        except Exception as e:
            logger.error(f"IA Error: {e}")
        return False, None

class LibGenProvider(Provider):
    def __init__(self):
        self.name = "LibGen"
        self.mirrors = [
            "https://libgen.is",
            "https://libgen.rs",
            "https://libgen.st"
        ]

    def search_and_download(self, query, safe_name):
        # Simplistic LibGen scraper fallback
        for mirror in self.mirrors:
            try:
                search_url = f"{mirror}/search.php"
                params = {"req": query, "res": 10, "column": "def"}
                r = requests.get(search_url, params=params, headers=HEADERS, timeout=15)
                if r.status_code != 200: continue
                
                soup = BeautifulSoup(r.content, "html.parser")
                # Look for MD5 links
                for a in soup.find_all("a"):
                    href = a.get("href", "")
                    if "md5=" in href:
                         # Resolve
                         # Note: LibGen scraping is brittle. 
                         # This acts as a backup if Anna's Archive fails.
                         pass 
                         # Implementing full LibGen scraper again is complex and redundancy 
                         # since Anna's Archive aggregates LibGen.
                         # Skipping detailed implementation for brevity unless requested.
            except Exception:
                pass
        return False, None

class OpenLibraryProvider(Provider):
    def __init__(self):
        self.name = "Open Library"
        self.search_url = "https://openlibrary.org/search.json"
        self.base_url = "https://openlibrary.org"
        
    def search_and_download(self, query, safe_name):
        try:
            params = {"q": query, "limit": 5}
            r = requests.get(self.search_url, params=params, headers=HEADERS, timeout=CONNECTION_TIMEOUT)
            if r.status_code != 200:
                return False, None
                
            data = r.json()
            docs = data.get("docs", [])
            if not docs:
                return False, None
            
            # Try each result
            for doc in docs:
                title = doc.get("title", "")
                # Check title similarity
                similarity = difflib.SequenceMatcher(None, query.lower(), title.lower()).ratio()
                if similarity < 0.4:
                    continue
                
                # Check if borrowable/readable
                ia_ids = doc.get("ia", [])
                if not ia_ids:
                    continue
                
                # Try to get Internet Archive ID
                for ia_id in ia_ids[:2]:  # Try first 2 IA IDs
                    ia_url = f"https://archive.org/download/{ia_id}/{ia_id}.pdf"
                    logger.info(f"  Trying Open Library via IA: {ia_id}")
                    
                    try:
                        filename = f"{safe_name}_openlibrary.pdf"
                        filepath = os.path.join(DOWNLOAD_DIR, filename)
                        
                        dl_r = requests.get(ia_url, headers=HEADERS, stream=True, timeout=DOWNLOAD_TIMEOUT)
                        if dl_r.status_code == 200:
                            with open(filepath, 'wb') as f:
                                for chunk in dl_r.iter_content(chunk_size=16384):
                                    f.write(chunk)
                            
                            # Validate file
                            file_size = os.path.getsize(filepath)
                            if file_size > 50000:
                                logger.info(f"  Downloaded from Open Library ({file_size / 1024 / 1024:.2f} MB): {filename}")
                                return True, filename
                            else:
                                os.remove(filepath)
                    except Exception as e:
                        logger.debug(f"  Failed to download {ia_id}: {e}")
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        continue
                        
        except Exception as e:
            logger.error(f"  Open Library search failed: {e}")
            
        return False, None

# --- MAIN ---

class BookDownloader:
    def __init__(self, book_list, use_fallback_providers=False):
        self.books = book_list
        # Only use Anna's Archive by default
        self.primary_provider = AnnasArchiveProvider()
        self.use_fallbacks = use_fallback_providers
        self.fallback_providers = [
            OpenAlexProvider(),
            InternetArchiveProvider(),
            OpenLibraryProvider(),  # Added Open Library
        ]
        self.history = self._load_history()
        self.failed_books = []  # Track books that AA couldn't find
        
        if not os.path.exists(DOWNLOAD_DIR):
            os.makedirs(DOWNLOAD_DIR)

    def _load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_history(self):
        try:
            with open(HISTORY_FILE, "w") as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save history: {e}")

    def process_book(self, book_query):
        # Check history first
        if book_query in self.history:
            fname = self.history[book_query]
            fpath = os.path.join(DOWNLOAD_DIR, fname)
            if os.path.exists(fpath) and os.path.getsize(fpath) > 10000:  # At least 10KB
                return {"query": book_query, "status": "Exists", "file": fname}
        
        safe_name = clean_filename(book_query)
        
        # Try Anna's Archive first
        try:
            logger.info(f"Searching Anna's Archive for '{book_query}'")
            success, filename = self.primary_provider.search_and_download(book_query, safe_name)
            if success:
                self.history[book_query] = filename
                self._save_history()
                return {"query": book_query, "status": "Downloaded", "provider": "Anna's Archive", "file": filename}
        except Exception as e:
            logger.error(f"Anna's Archive failed for '{book_query}': {e}")
        
        # If AA failed and we're allowed to use fallbacks
        if self.use_fallbacks:
            for provider in self.fallback_providers:
                try:
                    success, filename = provider.search_and_download(book_query, safe_name)
                    if success:
                        self.history[book_query] = filename
                        self._save_history()
                        return {"query": book_query, "status": "Downloaded", "provider": provider.name, "file": filename}
                except Exception as e:
                    logger.error(f"Provider {provider.name} failed for '{book_query}': {e}")
        else:
            # Track that AA couldn't find this book
            self.failed_books.append(book_query)
        
        return {"query": book_query, "status": "Missing"}

    def run(self):
        print(f"Starting download for {len(self.books)} books...")
        print(f"Using Anna's Archive (Playwright)")
        print(f"Max Workers: {MAX_WORKERS}")
        
        results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(self.process_book, book): book for book in self.books}
            
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(self.books), unit="book"):
                results.append(future.result())
        
        self.print_summary(results)
        return results

    def print_summary(self, results):
        print("\n" + "="*60)
        print("DOWNLOAD SUMMARY")
        print("="*60)
        success = 0
        for res in results:
            icon = "✅" if res["status"] in ["Downloaded", "Exists"] else "❌"
            msg = f"{icon} {res['query']}"
            if res["status"] == "Downloaded":
                msg += f" (via {res['provider']})"
                success += 1
            elif res["status"] == "Exists":
                success += 1
            print(msg)
        print("-" * 60)
        print(f"Total: {len(results)} | Success: {success} | Missing: {len(results) - success}")
        print("=" * 60)
        
        # Report on failed books
        if self.failed_books and not self.use_fallbacks:
            print(f"\n⚠️  {len(self.failed_books)} book(s) not found on Anna's Archive:")
            for book in self.failed_books:
                print(f"   - {book}")

if __name__ == "__main__":
    books_to_download = [
        "Stylistics: A Resource Book for Students Simpson 2004",
        "Reading Images: The Grammar of Visual Design Kress van Leeuwen 2006",
        "Language and the Internet Crystal 2006",
        "Exploring Digital Communication: Language in Action Tagg 2015",
        "Language and Gender Eckert McConnell-Ginet 2013",
        "Instagram: Visual Social Media Cultures Abidin 2020",
        "Digital Discourse: Language in the New Media Thurlow Mroczek 2011",
        "The Fashion System Barthes 1983",
        "Fashion as Communication Barnard 2002",
        "Orderly Fashion: A Sociology of Markets Aspers 2010",
        "Fashion at the Edge: Spectacle, Modernity, and Deathliness Evans 2013",
        "Exploring the Language of Poems, Plays and Prose Short 1996",
        "A Dictionary of Stylistics Wales 2014",
        "The Routledge Handbook of Stylistics Burke 2014",
        "Text and Context: Essays on Stylistics Hidalgo Downing Lavid 2009",
        "Stories and Social Media: Identities and Interaction Page 2012",
        "Critical Stylistics: The Power of English Jeffries 2010",
        "Introduction to Multimodal Analysis Machin 2007",
        "Discourse of Twitter and Social Media Zappavigna 2012",
        "Narrative: A Critical Linguistic Introduction Toolan 2012",
        "Multimodal Transcription and Text Analysis Baldry Thibault 2006",
        "Exploring English Grammar: From Formal to Functional Coffin Donohue North 2009",
        "Doing Visual Analysis: From Theory to Practice Ledin Machin 2020"
    ]
    
    # First pass: Only Anna's Archive
    print("\n" + "="*60)
    print("SEARCHING ANNA'S ARCHIVE ONLY")
    print("="*60 + "\n")
    
    downloader = BookDownloader(books_to_download, use_fallback_providers=False)
    results = downloader.run()
    
    # If there are failed books, ask user if they want to try other sources
    if downloader.failed_books:
        print(f"\n{'='*60}")
        print(f"Found {len(results) - len(downloader.failed_books)} books on Anna's Archive.")
        print(f"{len(downloader.failed_books)} books were not found.")
        print(f"{'='*60}\n")
        
        response = input("Would you like to search other sources (OpenAlex, Internet Archive) for missing books? (y/n): ")
        
        if response.lower() in ['y', 'yes']:
            print("\n" + "="*60)
            print("SEARCHING OTHER SOURCES FOR MISSING BOOKS")
            print("="*60 + "\n")
            
            fallback_downloader = BookDownloader(downloader.failed_books, use_fallback_providers=True)
            fallback_results = fallback_downloader.run()
            
            print("\n" + "="*60)
            print("FINAL SUMMARY")
            print("="*60)
            print(f"Anna's Archive: {len(results) - len(downloader.failed_books)} books")
            fallback_success = sum(1 for r in fallback_results if r['status'] in ['Downloaded', 'Exists'])
            print(f"Other Sources: {fallback_success} books")
            print(f"Total Downloaded: {len(results) - len(downloader.failed_books) + fallback_success}/{len(books_to_download)}")
            print("="*60)

