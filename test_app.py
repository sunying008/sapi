import pytest
from fastapi.testclient import TestClient
from datetime import datetime
import json
from app import app

client = TestClient(app)

def test_health_check():
    """测试健康检查接口"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_search_single_query():
    """测试单个查询"""
    response = client.post(
        "/search",
        json={"query": ["python programming"]}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # 验证基本结构
    assert "code" in data
    assert "log_id" in data
    assert "data" in data
    
    # 验证code
    assert data["code"] == 200
    
    # 验证log_id格式
    assert len(data["log_id"]) == 14  # YYYYMMDDhhmmss format
    
    # 验证搜索响应结构
    search_data = data["data"]
    assert search_data["_type"] == "SearchResponse"
    assert "queryContext" in search_data
    assert "webPages" in search_data
    assert "images" in search_data
    
    # 验证查询上下文
    assert search_data["queryContext"]["originalQuery"] == "python programming"
    
    # 验证网页结果
    web_pages = search_data["webPages"]
    assert "webSearchUrl" in web_pages
    assert "totalEstimatedMatches" in web_pages
    assert "value" in web_pages
    assert isinstance(web_pages["value"], list)
    
    # 验证至少有一个结果
    assert len(web_pages["value"]) > 0
    
    # 验证第一个结果的结构
    first_result = web_pages["value"][0]
    assert "id" in first_result
    assert "name" in first_result
    assert "url" in first_result
    assert "displayUrl" in first_result
    assert "snippet" in first_result
    assert "summary" in first_result

def test_search_multiple_queries():
    """测试多个查询"""
    response = client.post(
        "/search",
        json={"query": ["python", "javascript"]}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # 验证返回了两组结果
    assert isinstance(data["data"], list)
    assert len(data["data"]) == 2
    
    # 验证每组结果的结构
    for result in data["data"]:
        assert result["_type"] == "SearchResponse"
        assert "queryContext" in result
        assert "webPages" in result
        assert "images" in result

def test_search_empty_query():
    """测试空查询"""
    response = client.post(
        "/search",
        json={"query": []}
    )
    
    assert response.status_code == 422  # 验证参数错误

def test_search_invalid_request():
    """测试无效请求"""
    response = client.post(
        "/search",
        json={"invalid": "data"}
    )
    
    assert response.status_code == 422  # 验证参数错误

def test_search_result_fields():
    """测试搜索结果字段的完整性和格式"""
    response = client.post(
        "/search",
        json={"query": ["python"]}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    web_pages = data["data"]["webPages"]
    if len(web_pages["value"]) > 0:
        result = web_pages["value"][0]
        
        # 验证所有必需字段
        required_fields = [
            "id", "name", "url", "displayUrl", "snippet", 
            "summary", "siteName", "siteIcon", "datePublished", 
            "dateLastCrawled"
        ]
        for field in required_fields:
            assert field in result
        
        # 验证日期格式
        date_fields = ["datePublished", "dateLastCrawled"]
        for field in date_fields:
            if result[field]:
                # 验证ISO格式日期
                try:
                    datetime.fromisoformat(result[field].replace('Z', '+00:00'))
                except ValueError:
                    pytest.fail(f"Invalid date format in {field}: {result[field]}")

def test_search_large_query():
    """测试较长的查询字符串"""
    long_query = "a" * 1000  # 1000个字符的查询
    response = client.post(
        "/search",
        json={"query": [long_query]}
    )
    
    assert response.status_code == 200

def test_concurrent_searches():
    """测试并发搜索请求"""
    import asyncio
    import httpx
    
    async def make_request():
        async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/search",
                json={"query": ["python"]}
            )
            return response.status_code
    
    @pytest.mark.asyncio
    async def test():
        # 创建5个并发请求
        tasks = [make_request() for _ in range(5)]
        results = await asyncio.gather(*tasks)
        
        # 验证所有请求都成功
        for status_code in results:
            assert status_code == 200
    
    asyncio.run(test())
