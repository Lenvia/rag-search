import asyncio
import re

import aiohttp
import html2text


async def fetch_url(session, url):
    async with session.get(url) as response:
        try:
            response.raise_for_status()
            response.encoding = 'utf-8'
            html = await response.text()

            return html
        except Exception as e:
            print(f"fetch url failed: {url}: {e}")
            return ""


async def html_to_markdown(html):
    try:
        h = html2text.HTML2Text()
        h.ignore_links = True
        h.ignore_images = True

        markdown = h.handle(html)

        return markdown
    except Exception as e:
        print(f"html to markdown failed: {e}")
        return ""


async def fetch_markdown(session, url):
    try:
        html = await fetch_url(session, url)
        markdown = await html_to_markdown(html)
        markdown = re.sub(r'\n{2,n}', '\n', markdown)

        return url, markdown
    except Exception as e:
        print(f"fetch markdown failed: {url}: {e}")
        return url, ""


async def batch_fetch_urls(urls):
    """
    异步批量获取多个URL的内容。

    参数:
    urls - 包含多个URL的列表。

    返回值:
    results - 获取到的内容列表。如果某个URL获取失败，则对应位置为None。
    """
    print("urls", urls)
    try:
        # 创建一个异步的HTTP客户端会话
        async with aiohttp.ClientSession() as session:
            # 为每个URL创建一个异步获取任务
            tasks = [fetch_markdown(session, url) for url in urls]
            # 并行执行所有任务，并收集结果
            results = await asyncio.gather(*tasks, return_exceptions=False)
            print(results)
            return results
    except aiohttp.ClientResponseError as e:
        # 处理HTTP请求错误
        print(f"batch fetch urls failed: {e}")
        return []
