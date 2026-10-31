#!/usr/bin/env python3
"""
Anna's Archive Metadata Analyzer
Reads saved metadata and provides analysis tools
Can optionally visit individual pages for enhanced metadata collection
"""

import os
import json
import pandas as pd
import time
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.firefox import GeckoDriverManager
import logging
from datetime import datetime
import requests
from urllib.parse import urljoin

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MetadataAnalyzer:
    def __init__(self, metadata_dir=r"C:\Users\doren\PycharmProjects\Anna's Archive\annas_archive_metadata"):
        """
        Initialize the metadata analyzer

        Args:
            metadata_dir (str): Directory containing saved metadata files
        """
        self.metadata_dir = metadata_dir
        self.metadata = []
        self.enhanced_metadata = []

    def load_latest_metadata(self):
        """
        Load the most recent metadata file

        Returns:
            bool: True if metadata loaded successfully
        """
        try:
            # Find the most recent JSON file
            json_files = [f for f in os.listdir(self.metadata_dir) if f.endswith('.json') and 'metadata' in f]

            if not json_files:
                logger.error("No metadata JSON files found")
                return False

            # Sort by modification time and get the latest
            json_files.sort(key=lambda x: os.path.getmtime(os.path.join(self.metadata_dir, x)), reverse=True)
            latest_file = json_files[0]

            file_path = os.path.join(self.metadata_dir, latest_file)

            with open(file_path, 'r', encoding='utf-8') as f:
                self.metadata = json.load(f)

            logger.info(f"Loaded {len(self.metadata)} records from {latest_file}")
            return True

        except Exception as e:
            logger.error(f"Error loading metadata: {str(e)}")
            return False

    def analyze_metadata(self):
        """
        Perform basic analysis on the loaded metadata
        """
        if not self.metadata:
            logger.warning("No metadata loaded for analysis")
            return

        df = pd.DataFrame(self.metadata)

        print("\n" + "=" * 50)
        print("METADATA ANALYSIS REPORT")
        print("=" * 50)

        print(f"\nTotal Records: {len(df)}")

        # Search term distribution
        print(f"\nResults by Search Term:")
        search_counts = df['search_term'].value_counts()
        for term, count in search_counts.items():
            print(f"  {term}: {count}")

        # Format distribution
        print(f"\nFile Formats:")
        format_counts = df['format'].value_counts()
        for fmt, count in format_counts.items():
            print(f"  {fmt}: {count}")

        # Language distribution
        print(f"\nLanguages:")
        lang_counts = df['language'].value_counts().head(10)
        for lang, count in lang_counts.items():
            print(f"  {lang}: {count}")

        # Publication years
        years = df['year'].dropna()
        if not years.empty:
            years_numeric = pd.to_numeric(years, errors='coerce').dropna()
            if not years_numeric.empty:
                print(f"\nPublication Years:")
                print(f"  Range: {int(years_numeric.min())} - {int(years_numeric.max())}")
                print(f"  Most common: {years.value_counts().head(5).to_dict()}")

        # File sizes (if available)
        sizes = df['file_size'].dropna()
        if not sizes.empty:
            print(f"\nFile Sizes (sample):")
            print(f"  {sizes.value_counts().head(10).to_dict()}")

        print("\n" + "=" * 50)

    def filter_results(self, **criteria):
        """
        Filter metadata based on criteria

        Args:
            **criteria: Filtering criteria (e.g., format='pdf', language='English')

        Returns:
            list: Filtered metadata records
        """
        if not self.metadata:
            logger.warning("No metadata loaded")
            return []

        filtered = self.metadata.copy()

        for key, value in criteria.items():
            if key in ['search_term', 'format', 'language', 'year', 'book_type']:
                filtered = [item for item in filtered if value.lower() in str(item.get(key, '')).lower()]

        logger.info(f"Filtered to {len(filtered)} records based on criteria: {criteria}")
        return filtered

    def export_filtered_results(self, filtered_results, filename_suffix="filtered"):
        """
        Export filtered results to CSV and JSON

        Args:
            filtered_results (list): Filtered metadata records
            filename_suffix (str): Suffix for output filename
        """
        if not filtered_results:
            logger.warning("No filtered results to export")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Export to CSV
        csv_filename = os.path.join(self.metadata_dir, f"filtered_results_{filename_suffix}_{timestamp}.csv")
        df = pd.DataFrame(filtered_results)
        df.to_csv(csv_filename, index=False, encoding='utf-8')
        logger.info(f"Filtered results exported to: {csv_filename}")

        # Export to JSON
        json_filename = os.path.join(self.metadata_dir, f"filtered_results_{filename_suffix}_{timestamp}.json")
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(filtered_results, f, indent=2, ensure_ascii=False)
        logger.info(f"Filtered results exported to: {json_filename}")

    def generate_download_links_report(self, filtered_results=None):
        """
        Generate a report with all download links for manual use

        Args:
            filtered_results (list): Optional filtered results, otherwise uses all metadata
        """
        data = filtered_results if filtered_results else self.metadata

        if not data:
            logger.warning("No data available for link report")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = os.path.join(self.metadata_dir, f"download_links_report_{timestamp}.html")

        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Anna's Archive Download Links Report</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                table { border-collapse: collapse; width: 100%; }
                th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                th { background-color: #f2f2f2; }
                .link { color: blue; text-decoration: underline; }
                .metadata { font-size: 12px; color: #666; }
            </style>
        </head>
        <body>
            <h1>Anna's Archive Download Links Report</h1>
            <p>Generated: {timestamp}</p>
            <p>Total items: {count}</p>
            <table>
                <tr>
                    <th>Title</th>
                    <th>Authors</th>
                    <th>Format</th>
                    <th>Size</th>
                    <th>Link</th>
                    <th>Search Term</th>
                </tr>
        """.format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), count=len(data))

        for item in data:
            title = item.get('title', 'N/A')[:80]
            authors = item.get('authors', 'N/A')[:50]
            format_type = item.get('format', 'N/A')
            size = item.get('file_size', 'N/A')
            url = item.get('anna_archive_url', '')
            search_term = item.get('search_term', 'N/A')

            html_content += f"""
                <tr>
                    <td>{title}</td>
                    <td>{authors}</td>
                    <td>{format_type}</td>
                    <td>{size}</td>
                    <td><a href="{url}" target="_blank" class="link">Open Page</a></td>
                    <td>{search_term}</td>
                </tr>
            """

        html_content += """
            </table>
            <br>
            <p><strong>Usage Instructions:</strong></p>
            <ul>
                <li>Click "Open Page" links to visit individual book pages</li>
                <li>Each page contains download options (fast/slow partners)</li>
                <li>Choose appropriate download method based on your needs</li>
                <li>Always respect copyright and terms of service</li>
            </ul>
        </body>
        </html>
        """

        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"Download links report generated: {report_filename}")
        return report_filename


class EnhancedMetadataCollector:
    """
    Optional enhanced metadata collector that can visit individual pages
    USE RESPONSIBLY and in compliance with website terms of service
    """

    def __init__(self, delay_range=(3, 7)):
        """
        Initialize with human-like browsing patterns

        Args:
            delay_range (tuple): Range for random delays between requests
        """
        self.delay_range = delay_range
        self.driver = None

    def setup_browser(self, headless=True):
        """
        Setup browser with enhanced stealth settings
        """
        firefox_options = Options()
        if headless:
            firefox_options.add_argument("--headless")

        # Enhanced stealth settings
        firefox_options.set_preference("general.useragent.override",
                                       "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0")
        firefox_options.set_preference("dom.webdriver.enabled", False)
        firefox_options.set_preference("useAutomationExtension", False)

        # Additional privacy settings
        firefox_options.set_preference("privacy.trackingprotection.enabled", True)
        firefox_options.set_preference("geo.enabled", False)
        firefox_options.set_preference("media.navigator.enabled", False)

        executable_path = GeckoDriverManager().install()
        self.driver = webdriver.Firefox(executable_path=executable_path, options=firefox_options)

        # Remove webdriver property
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    def human_like_delay(self):
        """Add human-like delay between actions"""
        delay = random.uniform(*self.delay_range)
        time.sleep(delay)

    def collect_enhanced_metadata(self, url_list, max_items=10):
        """
        Collect enhanced metadata from a list of URLs

        Args:
            url_list (list): List of Anna's Archive URLs
            max_items (int): Maximum number of items to process

        Returns:
            list: Enhanced metadata
        """
        if not self.driver:
            logger.error("Browser not setup. Call setup_browser() first.")
            return []

        enhanced_data = []

        # Limit processing for demonstration
        urls_to_process = url_list[:max_items]

        logger.info(f"Collecting enhanced metadata for {len(urls_to_process)} items")

        for i, url in enumerate(urls_to_process, 1):
            try:
                logger.info(f"Processing {i}/{len(urls_to_process)}: {url}")

                # Human-like delay
                self.human_like_delay()

                # Visit the page
                self.driver.get(url)

                # Wait for page load
                time.sleep(random.uniform(2, 4))

                # Extract enhanced metadata
                enhanced_info = self.extract_page_metadata(url)
                enhanced_data.append(enhanced_info)

            except Exception as e:
                logger.error(f"Error processing {url}: {str(e)}")
                continue

        return enhanced_data

    def extract_page_metadata(self, url):
        """
        Extract enhanced metadata from an individual book page

        Args:
            url (str): The book page URL

        Returns:
            dict: Enhanced metadata
        """
        metadata = {
            'url': url,
            'extraction_time': datetime.now().isoformat(),
            'description': '',
            'download_options': [],
            'technical_details': {},
            'additional_info': ''
        }

        try:
            # Extract description
            try:
                desc_element = self.driver.find_element(By.CSS_SELECTOR, ".description, [class*='description']")
                metadata['description'] = desc_element.text.strip()
            except NoSuchElementException:
                pass

            # Extract download options (for metadata purposes only)
            try:
                download_sections = self.driver.find_elements(By.CSS_SELECTOR, "[class*='download']")
                for section in download_sections:
                    option_text = section.text.strip()
                    if option_text and len(option_text) > 5:
                        metadata['download_options'].append(option_text)
            except NoSuchElementException:
                pass

            # Extract technical details
            try:
                tech_elements = self.driver.find_elements(By.CSS_SELECTOR,
                                                          ".technical-details, [class*='tech'], [class*='detail']")
                for elem in tech_elements:
                    text = elem.text.strip()
                    if text:
                        metadata['technical_details'][elem.get_attribute('class')] = text
            except NoSuchElementException:
                pass

        except Exception as e:
            logger.error(f"Error extracting page metadata: {str(e)}")

        return metadata

    def close(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()


# Example usage functions
def main_analysis():
    """Main analysis workflow"""
    analyzer = MetadataAnalyzer()

    # Load and analyze metadata
    if analyzer.load_latest_metadata():
        analyzer.analyze_metadata()

        # Example filtering
        pdf_books = analyzer.filter_results(format='pdf')
        english_books = analyzer.filter_results(language='English')

        # Generate reports
        analyzer.export_filtered_results(pdf_books, "pdf_only")
        links_report = analyzer.generate_download_links_report(english_books)

        print(f"\nGenerated links report: {links_report}")
        print("You can open this HTML file in your browser to access individual book pages.")


def enhanced_collection_example():
    """
    Example of enhanced metadata collection
    WARNING: Use responsibly and in compliance with website terms
    """
    analyzer = MetadataAnalyzer()

    if analyzer.load_latest_metadata():
        # Get a small sample of URLs for demonstration
        sample_urls = [item['anna_archive_url'] for item in analyzer.metadata[:5]
                       if item.get('anna_archive_url')]

        if sample_urls:
            collector = EnhancedMetadataCollector()
            try:
                collector.setup_browser(headless=True)
                enhanced_data = collector.collect_enhanced_metadata(sample_urls, max_items=3)

                # Save enhanced metadata
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                enhanced_file = os.path.join(analyzer.metadata_dir, f"enhanced_metadata_{timestamp}.json")

                with open(enhanced_file, 'w', encoding='utf-8') as f:
                    json.dump(enhanced_data, f, indent=2, ensure_ascii=False)

                logger.info(f"Enhanced metadata saved to: {enhanced_file}")

            finally:
                collector.close()


if __name__ == "__main__":
    print("Anna's Archive Metadata Analyzer")
    print("=" * 40)
    print("1. Run basic analysis")
    print("2. Run enhanced collection (sample)")

    choice = input("\nEnter choice (1 or 2): ").strip()

    if choice == "1":
        main_analysis()
    elif choice == "2":
        print("\nWARNING: Enhanced collection visits individual pages.")
        print("Ensure you comply with website terms of service.")
        confirm = input("Continue? (yes/no): ").strip().lower()
        if confirm == "yes":
            enhanced_collection_example()
    else:
        print("Invalid choice. Running basic analysis...")
        main_analysis()