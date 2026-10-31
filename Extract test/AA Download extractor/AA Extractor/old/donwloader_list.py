#!/usr/bin/env python3
"""
Anna's Archive Metadata Extractor
Extracts metadata from search results instead of downloading files
Saves results to CSV and JSON formats
"""

import os
import time
import csv
import json
import pandas as pd
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
from datetime import datetime
import re

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AnnasArchiveMetadataExtractor:
    def __init__(self, output_dir=r"C:\Users\doren\PycharmProjects\Anna's Archive\annas_archive_metadata",
                 headless=False, wait_time=10, results_per_search=10):
        """
        Initialize the metadata extractor

        Args:
            output_dir (str): Directory to save output files
            headless (bool): Run browser in headless mode
            wait_time (int): Maximum wait time for elements
            results_per_search (int): Number of results to extract per search
        """
        self.base_url = "https://annas-archive.org"
        self.output_dir = output_dir
        self.wait_time = wait_time
        self.results_per_search = results_per_search
        self.all_results = []

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        # Setup Firefox options
        firefox_options = Options()
        if headless:
            firefox_options.add_argument("--headless")

        # Add user agent and other options to appear more human
        firefox_options.set_preference("general.useragent.override",
                                       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        firefox_options.set_preference("dom.webdriver.enabled", False)
        firefox_options.set_preference("useAutomationExtension", False)

        # Initialize driver
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

    def extract_metadata_from_results(self, search_terms):
        """
        Main method to process a list of search terms and extract metadata

        Args:
            search_terms (list): List of strings to search for
        """
        if not search_terms:
            logger.warning("No search terms provided")
            return

        successful_extractions = []
        failed_extractions = []

        for i, term in enumerate(search_terms, 1):
            logger.info(f"Processing {i}/{len(search_terms)}: '{term}'")
            try:
                results = self.extract_single_search_metadata(term)
                if results:
                    successful_extractions.append(term)
                    self.all_results.extend(results)
                    logger.info(f"Successfully extracted {len(results)} results for: '{term}'")
                else:
                    failed_extractions.append(term)
                    logger.warning(f"No results found for: '{term}'")
            except Exception as e:
                logger.error(f"Error processing '{term}': {str(e)}")
                failed_extractions.append(term)

            # Add delay between searches to be respectful
            time.sleep(3)

        # Save results
        self.save_results()

        # Print summary
        logger.info(f"\nSummary:")
        logger.info(f"Successful extractions: {len(successful_extractions)}")
        logger.info(f"Failed extractions: {len(failed_extractions)}")
        logger.info(f"Total results extracted: {len(self.all_results)}")

        if failed_extractions:
            logger.info(f"Failed terms: {failed_extractions}")

    def extract_single_search_metadata(self, search_term):
        """
        Extract metadata for a single search term

        Args:
            search_term (str): The term to search for

        Returns:
            list: List of dictionaries containing metadata for each result
        """
        try:
            logger.info(f"Navigating to Anna's Archive...")
            # Navigate to Anna's Archive
            self.driver.get(self.base_url)

            # Wait for page to load
            time.sleep(5)

            # Find search box
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
                    continue

            if not search_box:
                logger.error("Could not find search box")
                return []

            # Clear and enter search term
            search_box.clear()
            search_box.send_keys(search_term)
            search_box.send_keys(Keys.RETURN)

            # Wait for search results
            logger.info("Waiting for search results...")
            time.sleep(8)

            # Extract metadata from search results
            return self.parse_search_results_page(search_term)

        except Exception as e:
            logger.error(f"Error extracting metadata for '{search_term}': {str(e)}")
            return []

    def parse_search_results_page(self, search_term):
        """
        Parse the search results page and extract metadata

        Args:
            search_term (str): The original search term

        Returns:
            list: List of dictionaries containing metadata
        """
        results = []

        try:
            # Look for result containers - these are the main divs containing each book result
            result_containers = []

            # Try different selectors for result containers
            container_selectors = [
                "div.h-\\[110px\\]",  # Based on the HTML you provided
                ".h-\\[110px\\]",
                "div[class*='h-[110px]']",
                ".search-result",
                ".result-item",
                "div.flex.flex-col.justify-center"
            ]

            for selector in container_selectors:
                try:
                    containers = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if containers:
                        result_containers = containers
                        logger.info(f"Found {len(containers)} result containers with selector: {selector}")
                        break
                except Exception as e:
                    logger.debug(f"Container selector failed {selector}: {str(e)}")
                    continue

            if not result_containers:
                # Fallback: look for any links that might be results
                logger.warning("No result containers found, trying fallback approach")
                result_containers = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/md5/']")
                if result_containers:
                    logger.info(f"Found {len(result_containers)} result links as fallback")

            if not result_containers:
                logger.error("No search results found on page")
                return results

            # Limit to requested number of results
            containers_to_process = result_containers[:self.results_per_search]
            logger.info(f"Processing {len(containers_to_process)} results")

            for i, container in enumerate(containers_to_process):
                try:
                    metadata = self.extract_single_result_metadata(container, search_term, i + 1)
                    if metadata:
                        results.append(metadata)
                except Exception as e:
                    logger.error(f"Error extracting metadata from result {i + 1}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error parsing search results page: {str(e)}")

        return results

    def extract_single_result_metadata(self, container, search_term, result_number):
        """
        Extract metadata from a single search result container

        Args:
            container: Selenium WebElement containing the result
            search_term (str): Original search term
            result_number (int): Position in search results

        Returns:
            dict: Metadata dictionary
        """
        metadata = {
            'search_term': search_term,
            'result_number': result_number,
            'extraction_timestamp': datetime.now().isoformat(),
            'title': '',
            'authors': '',
            'publisher': '',
            'year': '',
            'language': '',
            'format': '',
            'file_size': '',
            'book_type': '',
            'source': '',
            'anna_archive_url': '',
            'description': '',
            'file_path': '',
            'md5_hash': ''
        }

        try:
            # Extract the main link and URL
            main_link = container.find_element(By.CSS_SELECTOR, "a")
            if main_link:
                anna_archive_url = main_link.get_attribute('href')
                metadata['anna_archive_url'] = anna_archive_url

                # Extract MD5 hash from URL
                if '/md5/' in anna_archive_url:
                    md5_match = re.search(r'/md5/([a-f0-9]{32})', anna_archive_url)
                    if md5_match:
                        metadata['md5_hash'] = md5_match.group(1)

            # Extract title
            try:
                title_element = container.find_element(By.CSS_SELECTOR, "h3")
                metadata['title'] = title_element.text.strip()
            except NoSuchElementException:
                # Try alternative selectors
                try:
                    title_element = container.find_element(By.CSS_SELECTOR, ".text-xl, .text-lg, h2, h4")
                    metadata['title'] = title_element.text.strip()
                except NoSuchElementException:
                    logger.debug(f"Could not find title for result {result_number}")

            # Extract file info (language, format, size, etc.) from the description line
            try:
                info_elements = container.find_elements(By.CSS_SELECTOR, ".text-gray-500, .text-xs")
                for info_elem in info_elements:
                    info_text = info_elem.text.strip()
                    if info_text:
                        metadata['description'] = info_text

                        # Parse specific information from the description
                        # Extract language
                        lang_match = re.search(r'([A-Za-z]+)\s*\[([a-z]{2})\]', info_text)
                        if lang_match:
                            metadata['language'] = f"{lang_match.group(1)} [{lang_match.group(2)}]"

                        # Extract format
                        format_match = re.search(r'\.([a-z0-9]+),', info_text)
                        if format_match:
                            metadata['format'] = format_match.group(1)

                        # Extract file size
                        size_match = re.search(r'([\d.]+\s*[KMGT]?B)', info_text)
                        if size_match:
                            metadata['file_size'] = size_match.group(1)

                        # Extract book type
                        type_match = re.search(r'📘\s*Book\s*\([^)]+\)|📗\s*Book\s*\([^)]+\)|📕\s*Book\s*\([^)]+\)',
                                               info_text)
                        if type_match:
                            metadata['book_type'] = type_match.group(0)

                        # Extract source/file path
                        if '/' in info_text and not info_text.startswith('http'):
                            # Look for file path patterns
                            path_parts = info_text.split('/')
                            if len(path_parts) > 2:
                                metadata['file_path'] = info_text

                        break
            except NoSuchElementException:
                logger.debug(f"Could not find file info for result {result_number}")

            # Extract publication info (publisher, year)
            try:
                pub_elements = container.find_elements(By.CSS_SELECTOR, "div:not(.text-gray-500)")
                for pub_elem in pub_elements:
                    pub_text = pub_elem.text.strip()
                    if pub_text and not pub_text.startswith('base score') and len(pub_text) > 10:
                        # This might be publication info
                        if any(char.isdigit() for char in pub_text):
                            # Extract year
                            year_match = re.search(r'\b(19|20)\d{2}\b', pub_text)
                            if year_match:
                                metadata['year'] = year_match.group(0)

                            # The rest might be publisher
                            publisher_text = re.sub(r'\b(19|20)\d{2}\b', '', pub_text).strip(' ,')
                            if publisher_text:
                                metadata['publisher'] = publisher_text
                        break
            except NoSuchElementException:
                logger.debug(f"Could not find publication info for result {result_number}")

            # Extract authors
            try:
                author_elements = container.find_elements(By.CSS_SELECTOR, ".italic, em")
                for auth_elem in author_elements:
                    auth_text = auth_elem.text.strip()
                    if auth_text and not auth_text.startswith('base score'):
                        metadata['authors'] = auth_text
                        break
            except NoSuchElementException:
                logger.debug(f"Could not find authors for result {result_number}")

            # Clean up empty fields
            metadata = {k: v.strip() if isinstance(v, str) else v for k, v in metadata.items()}

            logger.debug(f"Extracted metadata for result {result_number}: {metadata['title'][:50]}...")
            return metadata

        except Exception as e:
            logger.error(f"Error extracting metadata from single result: {str(e)}")
            return metadata

    def save_results(self):
        """
        Save extracted results to CSV and JSON files
        """
        if not self.all_results:
            logger.warning("No results to save")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save to CSV
        csv_filename = os.path.join(self.output_dir, f"annas_archive_metadata_{timestamp}.csv")
        try:
            df = pd.DataFrame(self.all_results)
            df.to_csv(csv_filename, index=False, encoding='utf-8')
            logger.info(f"Results saved to CSV: {csv_filename}")
        except Exception as e:
            logger.error(f"Error saving CSV: {str(e)}")

        # Save to JSON
        json_filename = os.path.join(self.output_dir, f"annas_archive_metadata_{timestamp}.json")
        try:
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(self.all_results, f, indent=2, ensure_ascii=False)
            logger.info(f"Results saved to JSON: {json_filename}")
        except Exception as e:
            logger.error(f"Error saving JSON: {str(e)}")

        # Save summary
        summary_filename = os.path.join(self.output_dir, f"extraction_summary_{timestamp}.txt")
        try:
            with open(summary_filename, 'w', encoding='utf-8') as f:
                f.write(f"Anna's Archive Metadata Extraction Summary\n")
                f.write(f"{'=' * 45}\n\n")
                f.write(f"Extraction Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total Results: {len(self.all_results)}\n")

                # Count by search term
                search_terms = {}
                for result in self.all_results:
                    term = result.get('search_term', 'Unknown')
                    search_terms[term] = search_terms.get(term, 0) + 1

                f.write(f"\nResults by Search Term:\n")
                for term, count in search_terms.items():
                    f.write(f"  {term}: {count} results\n")

                # Count by format
                formats = {}
                for result in self.all_results:
                    fmt = result.get('format', 'Unknown')
                    formats[fmt] = formats.get(fmt, 0) + 1

                f.write(f"\nResults by Format:\n")
                for fmt, count in formats.items():
                    f.write(f"  {fmt}: {count} results\n")

            logger.info(f"Summary saved to: {summary_filename}")
        except Exception as e:
            logger.error(f"Error saving summary: {str(e)}")

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
    # Create metadata extractor instance
    with AnnasArchiveMetadataExtractor(
            output_dir=r"C:\Users\doren\PycharmProjects\Anna's Archive\annas_archive_metadata",
            headless=False,
            results_per_search=3  # Extract top 3 results per search
    ) as extractor:

        # Load search terms from file
        search_terms = extractor.load_search_terms_from_file("test_data.txt")

        if search_terms:
            # Extract metadata for the search terms
            extractor.extract_metadata_from_results(search_terms)
        else:
            logger.error("No search terms loaded. Please check that test_data.txt exists and contains search terms.")
            # Fallback to example terms if file doesn't exist
            fallback_terms = [
                "Manufacturing Consent Noam Chomsky",
                "machine learning python",
                "data structures algorithms",
                "natural language processing",
                "deep learning"
            ]
            logger.info("Using fallback search terms...")
            extractor.extract_metadata_from_results(fallback_terms)