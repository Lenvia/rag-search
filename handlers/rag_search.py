import asyncio
import os
from typing import Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel

from services.document.query import query_results
from services.document.store import store_results
from services.search.serper import get_search_results
from services.web import batch_fetch_urls
from utils.resp import resp_err, resp_data

rag_router = APIRouter()


class RagSearchReq(BaseModel):
    """
    RagSearchReq 类定义了进行搜索请求时所需参数的数据模型。

    参数:
    - query: 搜索查询字符串。
    - locale: 本地化设置，用于指定搜索结果的语言和地区格式，默认为空字符串。
    - search_n: 搜索结果的数量，默认为10。
    - search_provider: 搜索服务提供商，默认为'google'。
    - is_reranking: 是否进行重新排名，默认为False。
    - is_detail: 是否获取详细结果，默认为False。
    - detail_top_k: 详细结果中返回的顶部结果数量，默认为6。
    - detail_min_score: 详细结果的最小得分，默认为0.70。
    - is_filter: 是否进行过滤，默认为False。
    - filter_min_score: 过滤的最小得分，默认为0.80。
    - filter_top_k: 过滤后返回的顶部结果数量，默认为6。
    """
    query: str
    locale: Optional[str] = ''
    search_n: Optional[int] = 10
    search_provider: Optional[str] = 'google'
    is_reranking: Optional[bool] = False
    is_detail: Optional[bool] = False
    detail_top_k: Optional[int] = 6
    detail_min_score: Optional[float] = 0.70
    is_filter: Optional[bool] = False
    filter_min_score: Optional[float] = 0.80
    filter_top_k: Optional[int] = 6


@rag_router.post("/rag-search")
async def rag_search(req: RagSearchReq, authorization: str = Header(None)):
    authApiKey = os.getenv("AUTH_API_KEY")
    apiKey = ""
    if authorization:
        apiKey = authorization.replace("Bearer ", "")
    if apiKey != authApiKey:
        return resp_err("Access Denied")

    if req.query == "":
        return resp_err("invalid params")

    try:
        search_results = []
        # 1. get search results
        try:
            search_results = search(req.query, req.search_n, req.locale)
        except Exception as e:
            return resp_err(f"get search results failed: {e}")

        # 2. reranking
        if req.is_reranking:
            try:
                search_results = reranking(search_results, req.query)
            except Exception as e:
                print(f"reranking search results failed: {e}")

        # 3. fetch details
        if req.is_detail:
            try:
                search_results = await fetch_details(search_results, req.detail_min_score, req.detail_top_k)
            except Exception as e:
                print(f"fetch search details failed: {e}")

        # 4. filter content
        if req.is_filter:
            try:
                search_results = filter_content(search_results, req.query, req.filter_min_score, req.filter_top_k)
            except Exception as e:
                print(f"filter content failed: {e}")

        return resp_data({
            "search_results": search_results,
        })
    except Exception as e:
        return resp_err(f"rag search failed: {e}")


def search(query, num, locale=''):
    params = {
        "q": query,
        "num": num
    }

    if locale:
        params["hl"] = locale

    try:
        search_results = get_search_results(params=params)

        return search_results
    except Exception as e:
        print(f"search failed: {e}")
        raise e


def reranking(search_results, query):  # 对全部向量召回结果按照score进行排序
    try:
        index = store_results(results=search_results)
        match_results = query_results(index, query, 0.00, len(search_results))
    except Exception as e:
        print(f"reranking search results failed: {e}")
        raise e

    score_maps = {}
    for result in match_results:
        score_maps[result["uuid"]] = result["score"]

    for result in search_results:
        if result["uuid"] in score_maps:
            result["score"] = score_maps[result["uuid"]]

    sorted_search_results = sorted(search_results,
                                   key=lambda x: (x['score']),
                                   reverse=True)

    return sorted_search_results


async def fetch_details(search_results, min_score=0.00, top_k=6):  # 对于前 top_k 个相关度较高的链接， 获取详情放到map中，按照之前rank的顺序插入
    urls = []
    for res in search_results:
        if len(urls) > top_k:
            break
        if res["score"] >= min_score:
            urls.append(res["link"])

    try:
        details = await batch_fetch_urls(urls)
    except Exception as e:
        print(f"fetch details failed: {e}")
        raise e

    content_maps = {}
    for url, content in details:
        content_maps[url] = content

    for result in search_results:
        if result["link"] in content_maps:
            result["content"] = content_maps[result["link"]]
            print(result['title'], result["content"])

    return search_results


def filter_content(search_results, query, filter_min_score=0.8, filter_top_k=10):  # 过滤掉内容不相关的，但并不按照内容排序，仍按照之前的顺序
    try:
        results_with_content = []
        for result in search_results:
            if "content" in result and len(result["content"]) > len(result["snippet"]):
                results_with_content.append(result)

        index = store_results(results=results_with_content)
        match_results = query_results(index, query, filter_min_score, filter_top_k)

    except Exception as e:
        print(f"filter content failed: {e}")
        raise e

    content_maps = {}
    for result in match_results:
        if result["uuid"] not in content_maps:
            content_maps[result["uuid"]] = ""
        else:
            content_maps[result["uuid"]] += result["content"]

    for result in search_results:
        if result["uuid"] in content_maps:
            result["content"] = content_maps[result["uuid"]]

    return search_results


async def test():
    query = "Lenvia是谁"
    search_results = search(query, 10)
    # print(search_results)

    search_results = await fetch_details(search_results)

    # sorted_search_results = reranking(search_results, query)
    # for ssr in sorted_search_results:
    #     print(ssr)


if __name__ == "__main__":
    asyncio.run(test())
    pass
