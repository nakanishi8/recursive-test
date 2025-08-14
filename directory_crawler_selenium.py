#!/usr/bin/env python3
"""
Selenium版ディレクトリリスティング巡回ツール

指定したCSSセレクタでDOM要素を取得し、リンクを再帰的に巡回してディレクトリとファイルをログに記録します。

使用方法:
    python directory_crawler_selenium.py [URL] [--max-depth DEPTH] [--delay SECONDS] [--selector CSS_SELECTOR]

例:
    python directory_crawler_selenium.py http://ftp.uk.debian.org/debian/ --selector "a"
    python directory_crawler_selenium.py http://ftp.uk.debian.org/debian/ --max-depth 3 --delay 1.0 --selector "a"
"""

import argparse
import logging
import sys
import time
from urllib.parse import urljoin, urlparse

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("crawler_selenium.log", encoding="utf-8"),
    ],
)

items_logger = logging.getLogger("items_selenium")
items_handler = logging.FileHandler("items_selenium.log", encoding="utf-8")
formatter = logging.Formatter("%(asctime)s - %(message)s")
items_handler.setFormatter(formatter)
items_logger.addHandler(items_handler)
items_logger.setLevel(logging.INFO)
items_logger.propagate = False


class SeleniumDirectoryCrawler:
    def __init__(self, max_depth=10, delay=0, selector="a"):
        self.max_depth = max_depth
        self.delay = delay
        self.selector = selector
        self.visited_urls = set()
        self.dirs_found = 0
        self.files_found = 0
        self.errors_count = 0
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        self.driver = webdriver.Chrome(options=chrome_options)

    def is_valid_link(self, href, name, base_url):
        if href in ["../", "./", "..", "."] or name in ["../", "./", "..", "."]:
            return False
        absolute_url = urljoin(base_url, href)
        base_parsed = urlparse(base_url)
        parsed_url = urlparse(absolute_url)
        return parsed_url.netloc == base_parsed.netloc

    def extract_links(self, base_url):
        elements = self.driver.find_elements("css selector", self.selector)
        directories = []
        files = []
        for elem in elements:
            href = elem.get_attribute("href")
            name = elem.text.strip()
            if not href or not self.is_valid_link(href, name, base_url):
                continue
            # ディレクトリかファイルか判定
            if href.endswith("/"):
                directories.append({"url": href, "name": name})
            else:
                files.append({"url": href, "name": name})
        return directories, files

    def crawl_url(self, url, current_depth=0):
        if current_depth >= self.max_depth:
            logging.info(f"Max depth {self.max_depth} reached for {url}")
            return
        if url in self.visited_urls:
            return
        self.visited_urls.add(url)
        try:
            logging.info(f"Crawling: {url} (depth: {current_depth})")
            self.driver.get(url)
            directories, files = self.extract_links(url)
            for dir_info in directories:
                items_logger.info(f"DIRECTORY: {dir_info['url']} - Name: {dir_info['name']}")
                self.dirs_found += 1
                if self.dirs_found % 10 == 0:
                    logging.info(f"Found {self.dirs_found} directories so far...")
            for file_info in files:
                items_logger.info(f"FILE: {file_info['url']} - Name: {file_info['name']}")
                self.files_found += 1
                if self.files_found % 100 == 0:
                    logging.info(f"Found {self.files_found} files so far...")
            for dir_info in directories:
                time.sleep(self.delay)
                self.crawl_url(dir_info["url"], current_depth + 1)
        except WebDriverException as e:
            logging.error(f"WebDriver error for {url}: {e}")
            self.errors_count += 1
        except Exception as e:
            logging.error(f"Unexpected error for {url}: {e}")
            self.errors_count += 1

    def start_crawling(self, base_url):
        logging.info("=" * 60)
        logging.info("Selenium Directory Crawler Starting")
        logging.info(f"Target URL: {base_url}")
        logging.info(f"Max depth: {self.max_depth}")
        logging.info(f"Delay: {self.delay} seconds")
        logging.info(f"CSS Selector: {self.selector}")
        logging.info("Directories and files will be logged to: items_selenium.log")
        logging.info("=" * 60)
        start_time = time.time()
        try:
            self.crawl_url(base_url)
        except KeyboardInterrupt:
            logging.info("Crawling interrupted by user")
        except Exception as e:
            logging.error(f"Crawling failed: {e}")
        end_time = time.time()
        duration = end_time - start_time
        logging.info("=" * 60)
        logging.info("Crawling Completed")
        logging.info(f"Duration: {duration:.2f} seconds")
        logging.info(f"URLs visited: {len(self.visited_urls)}")
        logging.info(f"Directories found: {self.dirs_found}")
        logging.info(f"Files found: {self.files_found}")
        logging.info(f"Errors: {self.errors_count}")
        logging.info("=" * 60)
        self.driver.quit()


def main():
    parser = argparse.ArgumentParser(
        description="Recursively crawl directory listings using Selenium and log directories and files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s http://ftp.uk.debian.org/debian/ --selector "a"
  %(prog)s http://ftp.uk.debian.org/debian/ --max-depth 3 --delay 1.0 --selector "a"
        """,
    )
    parser.add_argument(
        "url",
        nargs="?",
        default="http://ftp.uk.debian.org/debian/",
        help="URL to crawl (default: http://ftp.uk.debian.org/debian/)",
    )
    parser.add_argument("--max-depth", type=int, default=5, help="Maximum recursion depth (default: 5)")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between requests in seconds (default: 0.5)")
    parser.add_argument("--selector", type=str, default="a", help="CSS selector to find links (default: 'a')")
    args = parser.parse_args()
    if not args.url.startswith(("http://", "https://")):
        print(f"Error: Invalid URL format: {args.url}")
        sys.exit(1)
    crawler = SeleniumDirectoryCrawler(max_depth=args.max_depth, delay=args.delay, selector=args.selector)
    crawler.start_crawling(args.url)


if __name__ == "__main__":
    main()
