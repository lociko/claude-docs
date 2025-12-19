#!/usr/bin/env python3
"""Sync Claude Code documentation from sitemap."""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from pathlib import Path
import re


SITEMAP_URL = "https://code.claude.com/docs/sitemap.xml"
DOCS_DIR = Path("docs")
CONCURRENT_REQUESTS = 10


async def fetch_sitemap(session: aiohttp.ClientSession) -> list[str]:
    """Fetch sitemap and extract English doc URLs."""
    async with session.get(SITEMAP_URL) as resp:
        text = await resp.text()

    root = ET.fromstring(text)
    ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    urls = []
    for loc in root.findall(".//ns:loc", ns):
        url = loc.text
        # Only English docs (no language prefix like /de/, /ja/, etc.)
        if url and "/docs/" in url:
            path_after_docs = url.split("/docs/")[-1]
            # Skip if starts with language code
            if not re.match(r"^(de|es|fr|id|it|ja|ko|pt|ru|zh-CN|zh-TW)/", path_after_docs):
                urls.append(url)

    return urls


async def download_doc(session: aiohttp.ClientSession, url: str, semaphore: asyncio.Semaphore) -> tuple[str, bool]:
    """Download a single doc as markdown."""
    async with semaphore:
        md_url = url.rstrip("/") + ".md"
        try:
            async with session.get(md_url) as resp:
                if resp.status == 200:
                    content = await resp.text()

                    # Extract filename from URL
                    path_after_docs = url.split("/docs/")[-1].strip("/")
                    if not path_after_docs:
                        path_after_docs = "index"

                    filepath = DOCS_DIR / f"{path_after_docs}.md"
                    filepath.parent.mkdir(parents=True, exist_ok=True)
                    filepath.write_text(content, encoding="utf-8")

                    return url, True
                else:
                    return url, False
        except Exception as e:
            print(f"Error downloading {url}: {e}")
            return url, False


async def main():
    """Main sync function."""
    DOCS_DIR.mkdir(exist_ok=True)

    connector = aiohttp.TCPConnector(limit=CONCURRENT_REQUESTS)
    async with aiohttp.ClientSession(connector=connector) as session:
        print("Fetching sitemap...")
        urls = await fetch_sitemap(session)
        print(f"Found {len(urls)} English docs")

        semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
        tasks = [download_doc(session, url, semaphore) for url in urls]

        results = await asyncio.gather(*tasks)

        success = sum(1 for _, ok in results if ok)
        failed = sum(1 for _, ok in results if not ok)

        print(f"Downloaded: {success}, Failed: {failed}")

        if failed > 0:
            print("Failed URLs:")
            for url, ok in results:
                if not ok:
                    print(f"  - {url}")


if __name__ == "__main__":
    asyncio.run(main())
