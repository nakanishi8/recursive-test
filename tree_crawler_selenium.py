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
import time

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

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


class TreeCrawlerSelenium:
    def __init__(self, delay=1.0, selector=None, max_depth=3):
        self.delay = delay
        self.selector = selector or "div.disclosured__elements > table.companies__table > tbody > tr"
        self.max_depth = max_depth
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--proxy-server=socks5://127.0.0.1:9050")
        self.driver = webdriver.Chrome(options=chrome_options)
        self.visited = set()
        self.dirs_found = 0
        self.files_found = 0
        self.errors_count = 0

    def wait_for_tree(self):
        """ツリー表示が読み込まれるまで待機"""
        selector = "div.overflow.active div.news__modal div.disclosured__table div.disclosured__elements table.companies__table tbody tr td"
        # selector = (
        #     "div.overflow.active > div.news__modal > div.disclosured__table > div.disclosured__elements > table.companies__table > tbody tr td",
        # )
        try:
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
            time.sleep(self.delay)
        except TimeoutException:
            logging.error("ツリー表示の待機セレクタが見つかりませんでした")
            self.errors_count += 1
            return False
        return True

    def wait_for_click_tree(self, prev_tr_count=None):
        # tbody内のtr数が変化するまで待つ
        tbody_selector = "div.overflow.active div.news__modal div.disclosured__elements table.companies__table tbody"
        try:
            # 1. tr数が減るまで待つ
            WebDriverWait(self.driver, 10).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, f"{tbody_selector} tr")) < prev_tr_count
            )
            # 2. tr数が減ったあと、再び増えるまで待つ
            WebDriverWait(self.driver, 10).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, f"{tbody_selector} tr")) > 1
            )
            # if prev_tr_count is not None:
            #     # tr数が変化するまで待つ
            #     WebDriverWait(self.driver, 10).until(
            #         lambda d: len(d.find_elements(By.CSS_SELECTOR, f"{tbody_selector} tr")) != prev_tr_count
            #     )
            # # trが2つ以上になるまで待つ（ヘッダー＋データ行）
            # WebDriverWait(self.driver, 10).until(
            #     lambda d: len(d.find_elements(By.CSS_SELECTOR, f"{tbody_selector} tr")) >= 2
            # )
            time.sleep(self.delay)
        except TimeoutException:
            logging.error("ツリー表示の待機セレクタが見つかりませんでした")
            self.errors_count += 1
            return False
        return True

    def click_view_button(self, view_btn):
        try:
            view_btn.click()
            logging.info("Viewボタンをクリックしました")
            return True
        except NoSuchElementException:
            logging.error("Viewボタンが見つかりませんでした")
            self.errors_count += 1
            return False

    def get_tree_rows(self):
        return self.driver.find_elements(By.CSS_SELECTOR, self.selector)

    def crawl_tree(self, depth=0):
        if depth >= self.max_depth:
            logging.info(f"Max depth {self.max_depth} reached. Skipping further recursion.")
            return
        rows = self.get_tree_rows()
        if not rows or len(rows) < 2:
            logging.info("ツリーに有効な行がありません")
            return
        prev_tr_count = len(rows)
        # for i, row in enumerate(rows, start=1):
        index = 0
        while index < len(rows):
            row = rows[index]
            tds = row.find_elements(By.TAG_NAME, "td")
            if not tds or len(tds) < 3:
                continue
            name = tds[0].text.strip()
            type_ = tds[2].text.strip()
            index += 1
            if depth == 0:
                # トップ階層: 2行目以降がフォルダ/ファイル
                if type_ == "Folder":
                    items_logger.info(f"DIRECTORY: {name}")
                    self.dirs_found += 1
                    # フォルダをクリックして遷移
                    tds[0].click()
                    if self.wait_for_click_tree(prev_tr_count):
                        self.crawl_tree(depth + 1)
                        # 戻る（Backボタンをクリック）
                        back_row = self.driver.find_element(
                            By.CSS_SELECTOR,
                            "div.disclosured__elements > table.companies__table > tbody > tr:nth-child(2)",
                        )
                        back_row.click()
                        self.wait_for_click_tree(prev_tr_count)
                elif type_ == "File":
                    items_logger.info(f"FILE: {name}")
                    self.files_found += 1
            else:
                # トップ以外の階層: 2行目はBackボタン
                if index == 1:
                    continue
                if type_ == "Folder":
                    items_logger.info(f"DIRECTORY: {name}")
                    self.dirs_found += 1
                    tds[0].click()
                    if self.wait_for_click_tree(prev_tr_count):
                        self.crawl_tree(depth + 1)
                        back_row = self.driver.find_element(
                            By.CSS_SELECTOR,
                            "div.disclosured__elements > table.companies__table > tbody > tr:nth-child(2)",
                        )
                        back_row.click()
                        self.wait_for_click_tree(prev_tr_count)
                elif type_ == "File":
                    items_logger.info(f"FILE: {name}")
                    self.files_found += 1

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
                EC.presence_of_element_located(
                    (By.XPATH, '//div[@class="detailed__btns"]/button[normalize-space(text())="View"]')
                )
            )
            view_btn.click()
            # WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            # if self.click_view_button():
            if self.wait_for_tree():
                self.crawl_tree()
        except KeyboardInterrupt:
            logging.info("Crawling interrupted by user")
        except Exception as e:
            logging.error(f"Crawling failed: {e}")
            self.errors_count += 1
        end_time = time.time()
        duration = end_time - start_time
        logging.info("=" * 60)
        logging.info("Crawling Completed")
        logging.info(f"Duration: {duration:.2f} seconds")
        logging.info(f"Directories found: {self.dirs_found}")
        logging.info(f"Files found: {self.files_found}")
        logging.info(f"Errors: {self.errors_count}")
        logging.info("=" * 60)
        self.driver.quit()


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
    parser.add_argument("--selector", type=str, required=True, help="CSS selector for tree rows")
    parser.add_argument("--max-depth", type=int, default=3, help="Maximum recursion depth (default: 3)")
    args = parser.parse_args()
    crawler = TreeCrawlerSelenium(delay=args.delay, selector=args.selector, max_depth=args.max_depth)
    crawler.start(args.url)


if __name__ == "__main__":
    main()
