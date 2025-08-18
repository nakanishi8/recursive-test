#!/usr/bin/env python3
"""
Selenium版ツリークリック巡回ツール

指定URLにアクセスし、Viewボタンをクリックしてツリーを表示。
ツリー内のフォルダ・ファイルを再帰的にクリックで巡回し、ログに記録します。

使用方法:
    python tree_crawler_selenium.py [URL] [--delay SECONDS] [--selector CSS_SELECTOR]

"""

import argparse
import logging
import re
import time
import urllib
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import search_word

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("tree_crawler_selenium.log", encoding="utf-8"),
    ],
)
items_logger = logging.getLogger("tree_items_selenium")
items_handler = logging.FileHandler("tree_items_selenium.log", encoding="utf-8")
formatter = logging.Formatter("%(asctime)s - %(message)s")
items_handler.setFormatter(formatter)
items_logger.addHandler(items_handler)
items_logger.setLevel(logging.INFO)
items_logger.propagate = False

current_dir = Path(__file__).parent.resolve()
download_dir = current_dir / "download"


class TreeCrawlerSelenium:
    def __init__(self, delay=1.0, xpath=None, selector=None, max_depth=None):
        self.delay = delay
        self.view_button_xpath = xpath
        self.selector = selector or "div.disclosured__elements > table.companies__table > tbody > tr"
        self.td_child_selector = self.selector + ":nth-child(n+2)"
        self.download_dir = download_dir
        self.max_depth = max_depth
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1600,1024")
        chrome_options.add_argument("--proxy-server=socks5://127.0.0.1:9050")
        chrome_options.add_experimental_option(
            "prefs",
            {
                "download.default_directory": str(self.download_dir),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": False,
            },
        )
        self.driver = webdriver.Chrome(options=chrome_options)
        self.visited = set()
        self.dirs_found = 0
        self.files_found = 0
        self.warning_count = 0
        self.errors_count = 0
        self.search_results = []

    def wait_for_tree(self, max_retry=3):
        """ツリー表示が読み込まれるまで待機（Timeout時はリトライ）"""
        selector = "div.overflow.active div.news__modal div.disclosured__table div.disclosured__elements table.companies__table tbody tr td"
        for attempt in range(1, max_retry + 1):
            try:
                WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                time.sleep(self.delay)
                return True
            except TimeoutException:
                logging.warning(f"ツリー表示の待機セレクタが見つかりませんでした（{attempt}回目）")
                self.warning_count += 1
                if attempt < max_retry:
                    time.sleep(1)
        return False

    def wait_for_click_tree(self, prev_tr_count=None, max_retry=3):
        # tbody内のtr数が変化するまで待つ
        for attempt in range(1, max_retry + 1):
            try:
                # 1. tr数が減るまで待つ
                WebDriverWait(self.driver, 10).until(
                    lambda d: len(d.find_elements(By.CSS_SELECTOR, self.td_child_selector)) < prev_tr_count
                )
                # 2. tr数が減ったあと、再び増えるまで待つ
                WebDriverWait(self.driver, 10).until(
                    lambda d: len(d.find_elements(By.CSS_SELECTOR, self.td_child_selector)) > 1
                )
                time.sleep(self.delay)
            except TimeoutException:
                logging.warning("ツリー表示の待機セレクタが見つかりませんでした")
                self.warning_count += 1
                if attempt < max_retry:
                    time.sleep(1)

        return True

    def get_tree_rows(self):
        return self.driver.find_elements(By.CSS_SELECTOR, self.td_child_selector)

    def crawl_tree(self, depth=0, path=None):
        if path is None:
            path = []
        if self.max_depth and depth >= self.max_depth:
            logging.info(f"Max depth {self.max_depth} reached. Skipping further recursion.")
            return
        rows = self.get_tree_rows()
        if not rows or len(rows) < 2:
            logging.info("ツリーに有効な行がありません")
            return
        prev_tr_count = len(rows)
        index = 0
        while index < len(rows):
            try:
                row = rows[index]
                tds = row.find_elements(By.TAG_NAME, "td")
                if not tds or len(tds) < 3:
                    continue

                scroll_target = self.driver.find_element(By.CSS_SELECTOR, "div.disclosured__table")
                current_scroll = self.driver.execute_script("return arguments[0].scrollTop;", scroll_target)
                target_offset = self.driver.execute_script("return arguments[0].offsetTop;", tds[0])

                if current_scroll != target_offset:
                    self.driver.execute_script("arguments[0].scrollTop = arguments[1];", scroll_target, target_offset)

                name = tds[0].text.strip()
                type_ = tds[2].text.strip()
                index += 1
                current_path = path + [name]
                full_path = "/".join(current_path)
                if depth == 0:
                    # トップ階層: 2行目以降がフォルダ/ファイル
                    if type_ == "Folder":
                        items_logger.info(f"DIRECTORY: {full_path}")
                        self.dirs_found += 1
                        # フォルダをクリックして遷移
                        WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(tds[0])).click()
                        if self.wait_for_click_tree(prev_tr_count):
                            self.crawl_tree(depth + 1, current_path)
                            # 戻る（Backボタンをクリック）
                            back_row = self.driver.find_element(
                                By.CSS_SELECTOR,
                                self.td_child_selector,
                            )
                            back_row.click()
                            self.wait_for_click_tree(prev_tr_count)
                    elif type_ == "File":
                        items_logger.info(f"FILE: {full_path}")
                        self.files_found += 1

                        # 検索用のフォルダ名
                        search_dl_folder_name = "/".join(path)

                        # 検索用のファイル名
                        unquote_url = urllib.parse.unquote(name)
                        match = re.search(r"&name=([^&]+)", unquote_url)
                        match_result = match.group(1) if match else name
                        parsed_query = re.sub(r"%u([0-9A-Fa-f]{4})", r"\\u\1", match_result)
                        search_dl_file_name = parsed_query.encode("utf-8").decode("unicode-escape")

                        if search_word.is_include_search_word(
                            search_dl_folder_name, search_dl_file_name, self.search_results
                        ):
                            # 一旦ダウンロードはスキップ
                            if True:
                                pass
                            else:
                                try:
                                    self.driver.execute_script("arguments[0].click();", tds[0])
                                    self.wait_for_download(search_dl_file_name)
                                except TimeoutError:
                                    self.errors_count += 1
                                    items_logger.error("[FILE] DOWNLOAD TIMEOUT type: %s", full_path)
                    else:
                        items_logger.warning(f"Unknown type: {full_path}")
                else:
                    # トップ以外の階層: 2行目はBackボタン
                    if index == 1:
                        continue
                    if type_ == "Folder":
                        items_logger.info(f"DIRECTORY: {full_path}")
                        self.dirs_found += 1
                        WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(tds[0])).click()
                        if self.wait_for_click_tree(prev_tr_count):
                            self.crawl_tree(depth + 1, current_path)
                            back_row = self.driver.find_element(By.CSS_SELECTOR, self.td_child_selector)
                            back_row.click()
                            self.wait_for_click_tree(prev_tr_count)
                    elif type_ == "File":
                        items_logger.info(f"FILE: {full_path}")
                        self.files_found += 1

                        # 検索用のフォルダ名
                        search_dl_folder_name = "/".join(path)

                        # 検索用のファイル名
                        unquote_url = urllib.parse.unquote(name)
                        match = re.search(r"&name=([^&]+)", unquote_url)
                        match_result = match.group(1) if match else name
                        parsed_query = re.sub(r"%u([0-9A-Fa-f]{4})", r"\\u\1", match_result)
                        search_dl_file_name = parsed_query.encode("utf-8").decode("unicode-escape")

                        if search_word.is_include_search_word(
                            search_dl_folder_name, search_dl_file_name, self.search_results
                        ):
                            # 一旦ダウンロードはスキップ
                            if True:
                                pass
                            else:
                                try:
                                    self.driver.execute_script("arguments[0].click();", tds[0])
                                    self.wait_for_download(search_dl_file_name)
                                except TimeoutError:
                                    self.errors_count += 1
                                    items_logger.error("[FILE] DOWNLOAD TIMEOUT type: %s", full_path)

            except ElementClickInterceptedException:
                items_logger.warning(f"Element click intercepted: {full_path}")
                self.errors_count += 1

            except StaleElementReferenceException:
                rows = self.get_tree_rows()
                if index >= len(rows):
                    break

    def start(self, url):
        logging.info("=" * 60)
        logging.info("Tree Crawler Selenium Starting")
        logging.info(f"Target URL: {url}")
        logging.info(f"Delay: {self.delay} seconds")
        logging.info(f"Tree selector: {self.selector}")
        logging.info("Directories and files will be logged to: tree_items_selenium.log")
        logging.info("=" * 60)
        start_time = time.time()
        try:
            self.driver.get(url)
            view_btn = WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.XPATH, self.view_button_xpath))
            )
            view_btn.click()
            if self.wait_for_tree():
                self.crawl_tree()
        except KeyboardInterrupt:
            logging.info("Crawling interrupted by user")
        except Exception as e:
            logging.error(f"Crawling failed: {e}")
            self.errors_count += 1
        end_time = time.time()
        duration = end_time - start_time

        # 出力ファイルのパスを生成
        output_file_path = self.download_dir / "extract_search_words.xlsx"
        # 結果をXLSXファイルに書き込む
        search_word.write_to_xlsx(self.search_results, output_file_path)

        logging.info("=" * 60)
        logging.info("Crawling Completed")
        logging.info(f"Duration: {duration:.2f} seconds")
        logging.info(f"Directories found: {self.dirs_found}")
        logging.info(f"Files found: {self.files_found}")
        logging.info(f"Errors: {self.errors_count}")
        logging.info("=" * 60)
        self.driver.quit()

    def wait_for_download(self, filename, timeout=60):
        target_path = self.download_dir / filename
        crdownload_path = Path(str(target_path) + ".crdownload")

        for _ in range(timeout):
            if crdownload_path.exists():
                time.sleep(1)
                continue
            if target_path.exists():
                return target_path
            time.sleep(0.5)

        raise TimeoutError(f"Download timed out for {filename}")


def main():
    parser = argparse.ArgumentParser(
        description="Recursively crawl tree structure by clicking with Selenium and log directories and files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--url",
        type=str,
        required=True,
        help="URL to crawl",
    )
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between actions in seconds (default: 1.0)")
    parser.add_argument("--xpath", type=str, required=True, help="XPath for the view button")
    parser.add_argument("--selector", type=str, required=True, help="CSS selector for tree rows")
    parser.add_argument("--max-depth", type=int, default=None, help="Maximum recursion depth (default: None)")
    args = parser.parse_args()
    crawler = TreeCrawlerSelenium(delay=args.delay, xpath=args.xpath, selector=args.selector)
    crawler.start(args.url)


if __name__ == "__main__":
    main()
