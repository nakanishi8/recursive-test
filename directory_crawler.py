#!/usr/bin/env python3
"""
ディレクトリリスティングを再帰的に巡回してディレクトリとファイルをログに記録するツール

ディレクトリとファイルは一つのログファイル(items.log)に記録され、
各エントリの前に「DIRECTORY:」または「FILE:」が付けられます。

使用方法:
    python directory_crawler.py [URL] [--max-depth DEPTH] [--delay SECONDS]

例:
    python directory_crawler.py http://ftp.uk.debian.org/debian/
    python directory_crawler.py http://ftp.uk.debian.org/debian/ --max-depth 3 --delay 1.0
"""

import argparse
import logging
import sys
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("crawler.log", encoding="utf-8"),
    ],
)

# ディレクトリとファイルの統合ログ設定
items_logger = logging.getLogger("items")

# ファイルハンドラの設定
items_handler = logging.FileHandler("items.log", encoding="utf-8")

# フォーマッタの設定
formatter = logging.Formatter("%(asctime)s - %(message)s")
items_handler.setFormatter(formatter)

# ロガーにハンドラを追加
items_logger.addHandler(items_handler)
items_logger.setLevel(logging.INFO)

# コンソール出力を無効化（ファイルにのみ出力）
items_logger.propagate = False


class DirectoryCrawler:
    def __init__(self, max_depth=10, delay=0):
        """
        ディレクトリクローラーの初期化

        Args:
            max_depth (int): 最大再帰深度
            delay (float): リクエスト間の待機時間（秒）
        """
        self.max_depth = max_depth
        self.delay = delay
        self.visited_urls = set()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        )

        # 統計情報
        self.dirs_found = 0
        self.files_found = 0
        self.errors_count = 0

    def is_valid_link(self, href, base_url):
        """
        リンクが有効かどうかをチェック

        Args:
            href (str): リンクのhref属性
            base_url (str): ベースURL

        Returns:
            bool: 有効なリンクかどうか
        """
        # 親ディレクトリや現在ディレクトリは飛ばす
        if href in ["../", "./", "..", "."]:
            return False

        # 絶対URLに変換
        absolute_url = urljoin(base_url, href)

        # 同じドメインのみを処理
        base_parsed = urlparse(base_url)
        parsed_url = urlparse(absolute_url)

        return parsed_url.netloc == base_parsed.netloc

    def extract_links(self, html_content, base_url):
        """
        HTMLからリンクを抽出

        Args:
            html_content (str): HTML内容
            base_url (str): ベースURL

        Returns:
            tuple: (ディレクトリリスト, ファイルリスト)
        """
        soup = BeautifulSoup(html_content, "html.parser")
        links = soup.find_all("a", href=True)

        directories = []
        files = []

        for link in links:
            href = link["href"]
            link_text = link.get_text().strip()

            if not self.is_valid_link(href, base_url):
                continue

            absolute_url = urljoin(base_url, href)

            # ディレクトリかファイルかを判定
            if href.endswith("/"):
                directories.append({"url": absolute_url, "name": link_text, "href": href})
            else:
                files.append({"url": absolute_url, "name": link_text, "href": href})

        return directories, files

    def crawl_url(self, url, current_depth=0):
        """
        指定されたURLを巡回

        Args:
            url (str): 巡回するURL
            current_depth (int): 現在の深度
        """
        # 最大深度に達した場合は処理を停止
        if current_depth >= self.max_depth:
            logging.info(f"Max depth {self.max_depth} reached for {url}")
            return

        # 既に訪問済みのURLは飛ばす
        if url in self.visited_urls:
            return

        self.visited_urls.add(url)

        try:
            logging.info(f"Crawling: {url} (depth: {current_depth})")

            # リクエストを送信
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            # リンクを抽出
            directories, files = self.extract_links(response.text, url)

            # ディレクトリをログに記録
            for dir_info in directories:
                items_logger.info(f"DIRECTORY: {dir_info['url']} - Name: {dir_info['name']}")
                self.dirs_found += 1

                if self.dirs_found % 10 == 0:
                    logging.info(f"Found {self.dirs_found} directories so far...")

            # ファイルをログに記録
            for file_info in files:
                items_logger.info(f"FILE: {file_info['url']} - Name: {file_info['name']}")
                self.files_found += 1

                if self.files_found % 100 == 0:
                    logging.info(f"Found {self.files_found} files so far...")

            # ディレクトリを再帰的に探索
            for dir_info in directories:
                # 待機
                time.sleep(self.delay)

                # 再帰的にディレクトリを探索
                self.crawl_url(dir_info["url"], current_depth + 1)

        except requests.exceptions.RequestException as e:
            logging.error(f"Request error for {url}: {e}")
            self.errors_count += 1
        except Exception as e:
            logging.error(f"Unexpected error for {url}: {e}")
            self.errors_count += 1

    def start_crawling(self, base_url):
        """
        クローリングを開始

        Args:
            base_url (str): 開始URL
        """
        logging.info("=" * 60)
        logging.info("Directory Crawler Starting")
        logging.info(f"Target URL: {base_url}")
        logging.info(f"Max depth: {self.max_depth}")
        logging.info(f"Delay: {self.delay} seconds")
        logging.info("Directories and files will be logged to: items.log")
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

        # 統計情報を表示
        logging.info("=" * 60)
        logging.info("Crawling Completed")
        logging.info(f"Duration: {duration:.2f} seconds")
        logging.info(f"URLs visited: {len(self.visited_urls)}")
        logging.info(f"Directories found: {self.dirs_found}")
        logging.info(f"Files found: {self.files_found}")
        logging.info(f"Errors: {self.errors_count}")
        logging.info("=" * 60)


def main():
    """
    メイン関数
    """
    parser = argparse.ArgumentParser(
        description="Recursively crawl directory listings and log directories and files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s http://ftp.uk.debian.org/debian/
  %(prog)s http://ftp.uk.debian.org/debian/ --max-depth 3 --delay 1.0
        """,
    )

    parser.add_argument(
        "url",
        nargs="?",
        default="http://ftp.uk.debian.org/debian/",
        help="URL to crawl (default: http://ftp.uk.debian.org/debian/)",
    )

    parser.add_argument("--max-depth", type=int, default=5, help="Maximum recursion depth (default: 5)")

    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between requests in seconds (default: 0.5)",
    )

    args = parser.parse_args()

    # URLが正しい形式かチェック
    if not args.url.startswith(("http://", "https://")):
        print(f"Error: Invalid URL format: {args.url}")
        sys.exit(1)

    # クローラーを作成して開始
    crawler = DirectoryCrawler(max_depth=args.max_depth, delay=args.delay)
    crawler.start_crawling(args.url)


if __name__ == "__main__":
    main()
