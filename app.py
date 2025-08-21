from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
import pytz
import logging
import traceback
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from ddgs import DDGS
from urllib.parse import urlparse

# 配置日志
# 创建带时间戳的日志文件名
log_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = f'execution_{log_timestamp}.log'

# 清除所有现有的处理器
logging.getLogger().handlers.clear()

# 创建文件处理器
file_handler = logging.FileHandler(log_filename, mode='w', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# 创建控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# 配置根日志器
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# 确保uvicorn也使用我们的日志配置
logging.getLogger("uvicorn").handlers = [file_handler, console_handler]
logging.getLogger("uvicorn.access").handlers = [file_handler, console_handler]
logging.getLogger("uvicorn.error").handlers = [file_handler, console_handler]

logger = logging.getLogger(__name__)

# 记录日志文件名
logger.info(f"Logging to file: {log_filename}")
logger.info(f"Search API starting up...")
logger.debug("Debug logging is enabled")

app = FastAPI(title="Search API")

# 添加启动事件来确保日志正常工作
@app.on_event("startup")
async def startup_event():
    logger.info("FastAPI application starting up")
    logger.info("All logging handlers configured")
    # 强制刷新日志
    for handler in logging.root.handlers:
        if hasattr(handler, 'flush'):
            handler.flush()

# 添加关闭事件来确保日志被保存
@app.on_event("shutdown")  
async def shutdown_event():
    logger.info("FastAPI application shutting down")
    # 强制刷新并关闭日志
    for handler in logging.root.handlers:
        if hasattr(handler, 'flush'):
            handler.flush()
        if hasattr(handler, 'close'):
            handler.close()

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加日志中间件
@app.middleware("http")
async def log_requests(request, call_next):
    import time
    start_time = time.time()
    
    # 记录请求开始
    logger.info(f"Request started: {request.method} {request.url}")
    logger.debug(f"Request headers: {dict(request.headers)}")
    
    # 强制刷新日志
    for handler in logging.root.handlers:
        if hasattr(handler, 'flush'):
            handler.flush()
    
    response = await call_next(request)
    
    # 记录请求完成
    process_time = time.time() - start_time
    logger.info(f"Request completed: {request.method} {request.url} - Status: {response.status_code} - Time: {process_time:.3f}s")
    
    # 再次强制刷新日志
    for handler in logging.root.handlers:
        if hasattr(handler, 'flush'):
            handler.flush()
    
    return response

class SearchRequest(BaseModel):
    query: List[str]  # 支持批量查询
    
    @validator('query')
    def validate_query(cls, v):
        if not v:
            raise ValueError("Query list cannot be empty")
        if any(not q.strip() for q in v):
            raise ValueError("Query strings cannot be empty")
        return v

# 添加错误处理
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global error handler caught: {str(exc)}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "log_id": datetime.now().strftime('%Y%m%d%H%M%S'),
            "msg": str(exc),
            "data": None,
            "traceback": traceback.format_exc() if logging.getLogger().level == logging.DEBUG else None
        }
    )

class WebPage(BaseModel):
    id: str
    name: str  # 标题
    url: str
    displayUrl: str
    snippet: str
    summary: str
    siteName: Optional[str] = None
    siteIcon: Optional[str] = None
    datePublished: Optional[str] = None
    dateLastCrawled: Optional[str] = None
    cachedPageUrl: Optional[str] = None
    language: Optional[str] = None
    isFamilyFriendly: Optional[bool] = None
    isNavigational: Optional[bool] = None
    # 新增字段
    mainContent: Optional[str] = None
    cleanText: Optional[str] = None
    metaInfo: Optional[Dict[str, Any]] = None
    pageImages: Optional[List[Dict[str, str]]] = None
    extractionStatus: Optional[str] = None

class WebPages(BaseModel):
    webSearchUrl: str
    totalEstimatedMatches: int
    value: List[WebPage]
    someResultsRemoved: bool = False

class Image(BaseModel):
    webSearchUrl: Optional[str] = None
    name: Optional[str] = None
    thumbnailUrl: Optional[str] = None
    datePublished: Optional[str] = None
    contentUrl: str
    hostPageUrl: str
    contentSize: Optional[str] = None
    encodingFormat: Optional[str] = None
    hostPageDisplayUrl: str
    width: int = 0
    height: int = 0
    thumbnail: Optional[Dict[str, Any]] = None

class Images(BaseModel):
    id: Optional[str] = None
    readLink: Optional[str] = None
    webSearchUrl: Optional[str] = None
    value: List[Image]
    isFamilyFriendly: Optional[bool] = None

class SearchResponse(BaseModel):
    code: int = 200
    log_id: str
    msg: Optional[str] = None
    data: Union[Dict[str, Any], List[Dict[str, Any]]]

def format_date(date_str: Optional[str] = None) -> str:
    """格式化日期为API标准格式"""
    if not date_str:
        now = datetime.now(pytz.UTC)
    else:
        try:
            now = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            now = datetime.now(pytz.UTC)
    return now.strftime('%Y-%m-%dT%H:%M:%S%z')

async def test_network_connectivity(url: str) -> bool:
    """Test basic network connectivity to a domain"""
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # Simple DNS resolution test
        import socket
        socket.gethostbyname(domain)
        logger.debug(f"DNS resolution successful for domain: {domain}")
        return True
    except Exception as e:
        logger.error(f"Network connectivity test failed for {domain}: {str(e)}")
        return False

async def extract_page_content(url: str) -> Dict[str, Any]:
    """
    提取网页的详细内容
    返回：
    - main_content: 主要内容
    - meta_info: 元数据信息
    - images: 页面图片
    - clean_text: 清理后的文本
    """
    logger.debug(f"Starting content extraction for URL: {url}")
    
    if not url:
        logger.error("Empty URL provided")
        return {
            'url': url,
            'status': 'error',
            'error': 'Empty URL provided'
        }
        
    if not url.startswith(('http://', 'https://')):
        logger.error(f"Invalid URL scheme: {url}")
        return {
            'url': url,
            'status': 'error',
            'error': 'Invalid URL scheme'
        }
    
    # Skip problematic domains that commonly fail
    parsed_url = urlparse(url)
    problematic_domains = ['youtube.com', 'www.youtube.com', 'youtu.be']
    if parsed_url.netloc.lower() in problematic_domains:
        logger.warning(f"Skipping problematic domain: {parsed_url.netloc}")
        return {
            'url': url,
            'status': 'skipped',
            'error': f'Domain {parsed_url.netloc} is known to have connectivity issues'
        }
    
    # Test network connectivity first
    if not await test_network_connectivity(url):
        logger.error(f"Network connectivity test failed for {url}")
        return {
            'url': url,
            'status': 'error',
            'error': 'Network connectivity test failed - DNS resolution or network issue'
        }
        
    try:
        # Increase timeout and add connection timeout
        timeout = aiohttp.ClientTimeout(total=45, connect=10)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }
        
        # Create connector with DNS and SSL configuration
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=30,
            ttl_dns_cache=300,
            use_dns_cache=True,
            ssl=False if 'localhost' in url or '127.0.0.1' in url else True,
            enable_cleanup_closed=True
        )
        
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            logger.debug(f"Sending HTTP request to: {url}")
            
            # Retry logic for network issues
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    async with session.get(url, headers=headers, allow_redirects=True) as response:
                        if response.status != 200:
                            logger.error(f"HTTP {response.status} error for URL: {url}")
                            return {
                                'url': url,
                                'status': 'error',
                                'error': f'HTTP {response.status}'
                            }
                        
                        logger.debug(f"Successfully received response from: {url}")
                        content_type = response.headers.get('Content-Type', '')
                        if 'text/html' not in content_type.lower():
                            logger.error(f"Unsupported content type: {content_type}")
                            return {
                                'url': url,
                                'status': 'error',
                                'error': f'Unsupported content type: {content_type}'
                            }
                        
                        # 尝试检测和使用正确的字符编码
                        charset = None
                        content_type = response.headers.get('Content-Type', '').lower()
                        if 'charset=' in content_type:
                            charset = content_type.split('charset=')[-1].strip()
                        
                        try:
                            text = await response.text(encoding=charset)
                        except UnicodeDecodeError:
                            # 如果指定编码失败，尝试使用常见的中文编码
                            for encoding in ['utf-8', 'gb2312', 'gbk', 'gb18030']:
                                try:
                                    text = await response.text(encoding=encoding)
                                    break
                                except UnicodeDecodeError:
                                    continue
                        
                        logger.debug(f"Response text length: {len(text)} characters")
                        if not text.strip():
                            logger.error("Empty response received")
                            return {
                                'url': url,
                                'status': 'error',
                                'error': 'Empty response received'
                            }
                        
                        try:
                            soup = BeautifulSoup(text, 'html.parser')
                        except Exception as e:
                            logger.error(f"Failed to parse HTML: {str(e)}")
                            return {
                                'url': url,
                                'status': 'error',
                                'error': f'HTML parsing failed: {str(e)}'
                            }
                        
                        # If we reach here, the request was successful
                        break
                        
                except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError, 
                        aiohttp.ClientOSError, OSError) as network_error:
                    if attempt < max_retries:
                        logger.warning(f"Network error on attempt {attempt + 1}/{max_retries + 1} for {url}: {str(network_error)}")
                        await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
                        continue
                    else:
                        logger.error(f"All retry attempts failed for {url}: {str(network_error)}")
                        return {
                            'url': url,
                            'status': 'error',
                            'error': f'Network connection failed after {max_retries + 1} attempts: {str(network_error)}'
                        }
                except Exception as e:
                    logger.error(f"Unexpected error during request to {url}: {str(e)}")
                    return {
                        'url': url,
                        'status': 'error',
                        'error': f'Request failed: {str(e)}'
                    }
        
        # 移除不需要的元素
        for tag in soup(['script', 'style', 'nav', 'footer', 'iframe']):
            tag.decompose()
        
        # 提取元数据
        meta_info = {
            'title': soup.title.string if soup.title else None,
            'description': soup.find('meta', {'name': 'description'})['content'] if soup.find('meta', {'name': 'description'}) else None,
            'keywords': soup.find('meta', {'name': 'keywords'})['content'] if soup.find('meta', {'name': 'keywords'}) else None,
            'author': soup.find('meta', {'name': 'author'})['content'] if soup.find('meta', {'name': 'author'}) else None,
        }
        
        # 提取主要内容
        main_content = ''
        
        # 检查是否是知乎或维基百科页面
        is_zhihu = 'zhihu.com' in url.lower()
        is_wikipedia = 'wikipedia.org' in url.lower()
        
        if is_wikipedia:
            # Wikipedia特定的内容提取
            content_div = soup.find('div', {'id': 'mw-content-text'})
            if content_div:
                # Remove unwanted sections
                for unwanted in content_div.find_all(['div', 'table'], class_=['navbox', 'vertical-navbox', 'infobox', 'reference', 'references']):
                    unwanted.decompose()
                
                # Get all paragraphs
                paragraphs = content_div.find_all('p')
                main_content = '\n'.join(p.get_text().strip() for p in paragraphs if p.get_text().strip())
        
        if is_zhihu:
            # 知乎特定的内容提取
            # 1. 尝试获取问题描述
            question_content = soup.find('div', class_='QuestionHeader-detail')
            if question_content:
                main_content = question_content.get_text(strip=True)
            
            # 2. 尝试获取回答内容
            answer_content = soup.find('div', class_='RichContent-inner')
            if answer_content:
                main_content = f"{main_content}\n\n{answer_content.get_text(strip=True)}" if main_content else answer_content.get_text(strip=True)
            
            # 3. 如果是文章页面
            article_content = soup.find('div', class_='Post-RichText')
            if article_content:
                main_content = article_content.get_text(strip=True)
        
        # 如果不是知乎或者没有找到知乎特定的内容，使用通用提取方法
        if not main_content:
            # 1. 首先尝试查找带有特定class的标签
            main_tags = soup.find_all(['article', 'main', 'div'], class_=['content', 'article', 'post', 'entry', 'entry-content', 'post-content', 'RichContent', 'RichContent-inner'])
            
            # 2. 如果没找到，尝试查找常见的主要内容容器
            if not main_tags:
                main_tags = soup.find_all(['article', 'main', 'section', 'div'], 
                                        id=['content', 'main', 'article', 'post'])
            
            # 3. 如果还是没找到，查找所有大文本块
            if not main_tags:
                main_tags = [tag for tag in soup.find_all(['div', 'section']) 
                           if len(tag.get_text(strip=True)) > 200]  # 只选择文本长度超过200的块
            
            if main_tags:
                # 选择最长的内容块
                main_content = max(main_tags, key=lambda x: len(x.get_text(strip=True))).get_text(strip=True)
            
            # 4. 如果上述方法都失败，则收集所有段落
            if not main_content:
                paragraphs = soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                main_content = ' '.join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20)
        
        # 确保内容不为空
        if not main_content:
            # 如果还是没有找到内容，提取所有可见文本
            main_content = soup.get_text(strip=True)
        
        # 提取图片
        images = []
        for img in soup.find_all('img'):
            src = img.get('src')
            if src:
                if not src.startswith(('http://', 'https://')):
                    # 处理相对路径
                    base_url = '{uri.scheme}://{uri.netloc}'.format(uri=urlparse(url))
                    src = str(aiohttp.yarl.URL(base_url).join(aiohttp.yarl.URL(src)))
                images.append({
                    'url': src,
                    'alt': img.get('alt', ''),
                    'title': img.get('title', '')
                })
        
        # 清理文本
        clean_text = ' '.join(main_content.split())
        
        return {
            'meta_info': meta_info,
            'main_content': main_content[:5000],  # 限制内容长度
            'images': images[:10],  # 限制图片数量
            'clean_text': clean_text[:1000],  # 限制清理文本长度
            'url': url,
            'status': 'success'
        }
        
    except Exception as e:
        logger.error(f"Error extracting content from {url}: {str(e)}")
        return {
            'url': url,
            'status': 'error',
            'error': str(e)
        }

@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    try:
        # Log network diagnostic information
        import socket
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            logger.info(f"System network info - Hostname: {hostname}, Local IP: {local_ip}")
        except Exception as e:
            logger.warning(f"Could not get network info: {str(e)}")
        
        logger.info(f"Starting search request with queries: {request.query}")
        all_results = []
        
        for query in request.query:
            logger.debug(f"Processing query: {query}")
            web_pages = []
            
            try:
                import os
                # Disable proxies and add DNS settings
                os.environ['HTTP_PROXY'] = ''
                os.environ['HTTPS_PROXY'] = ''
                
                # Log network environment
                logger.debug(f"Network environment - HTTP_PROXY: {os.environ.get('HTTP_PROXY', 'None')}")
                logger.debug(f"Network environment - HTTPS_PROXY: {os.environ.get('HTTPS_PROXY', 'None')}")
                
                with DDGS() as ddgs:
                    logger.debug(f"Initializing DDGS search for query: {query}")
                    
                    try:
                        # 执行搜索并获取结果
                        search_results = list(ddgs.text(query, max_results=10))
                        logger.debug(f"Found {len(search_results)} results for query: {query}")
                        
                        # 格式化结果
                        for idx, result in enumerate(search_results):
                            logger.debug(f"Processing result {idx}: {result}")  # 记录完整的结果
                            try:
                                # 验证并获取URL - DuckDuckGo返回的结果可能使用不同的键名
                                url = result.get("link") or result.get("url") or result.get("href")
                                if not url:
                                    logger.error(f"No URL found in result {idx}")
                                    continue
                                
                                # 修正URL格式
                                if not url.startswith(('http://', 'https://')):
                                    url = f'https://{url}' if not url.startswith('//') else f'https:{url}'
                                    
                                # 提取页面详细内容
                                page_content = await extract_page_content(url)
                                logger.debug(f"Extraction status for {url}: {page_content.get('status')}")
                                
                                if page_content.get('status') == 'error':
                                    logger.error(f"Content extraction failed for {url}: {page_content.get('error')}")
                                
                                # 处理和合并内容
                                search_result_text = result.get("body", "").strip()
                                extracted_content = page_content.get('clean_text', "").strip()
                                
                                # 合并搜索结果和提取的内容
                                combined_text = ""
                                if search_result_text:
                                    combined_text = search_result_text
                                if extracted_content:
                                    combined_text = f"{combined_text}\n\n{extracted_content}" if combined_text else extracted_content
                                
                                web_page = WebPage(
                                    id=f"https://api.search.com/v1/#WebPages.{idx}",
                                    name=result.get("title", "") or "Untitled",
                                    url=url,
                                    displayUrl=url,
                                    snippet=result.get("body", "") or "",
                                    summary=result.get("body", "") or "",  # 保持原有的summary
                                    siteName=result.get("source", "") or "",
                                    siteIcon=f"https://th.search.com/favicon?domain_url={result.get('link', '')}",
                                    datePublished=format_date(result.get("published")),
                                    dateLastCrawled=format_date(),
                                    cachedPageUrl=None,
                                    language=None,
                                    isFamilyFriendly=None,
                                    isNavigational=None,
                                    # 添加新的内容字段
                                    mainContent=page_content.get('main_content'),
                                    cleanText=combined_text,  # 使用合并后的文本
                                    metaInfo=page_content.get('meta_info'),
                                    pageImages=page_content.get('images'),
                                    extractionStatus=page_content.get('status')
                                )
                                web_pages.append(web_page)
                            except Exception as result_error:
                                logger.error(f"Error processing result {idx}: {str(result_error)}")
                                logger.debug(f"Problematic result data: {result}")
                                continue
                    except Exception as search_error:
                        logger.error(f"Error during search: {str(search_error)}")
                        raise HTTPException(
                            status_code=500,
                            detail=f"Search failed for query '{query}': {str(search_error)}"
                        )
            except Exception as query_error:
                logger.error(f"Error processing query '{query}': {str(query_error)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to process query '{query}': {str(query_error)}"
                )

            # 构建WebPages对象
            web_pages_result = WebPages(
                webSearchUrl=f"https://search.com/search?q={query}",
                totalEstimatedMatches=len(web_pages),
                value=web_pages,
                someResultsRemoved=False
            )

            # 构建空的Images对象（因为DuckDuckGo API没有直接提供图片）
            images_result = Images(
                value=[]
            )

            # 构建完整的响应
            all_results.append({
                "_type": "SearchResponse",
                "queryContext": {
                    "originalQuery": query
                },
                "webPages": web_pages_result.dict(),
                "images": images_result.dict(),
                "videos": None
            })

        # 如果只有一个查询，返回单个结果，否则合并结果
        final_data = all_results[0] if len(all_results) == 1 else all_results

        return SearchResponse(
            code=200,
            log_id=datetime.now().strftime('%Y%m%d%H%M%S'),
            msg=None,
            data=final_data
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    logger.info("Health check endpoint accessed")
    health_status = {"status": "healthy", "network_tests": {}}
    
    # Test connectivity to common domains
    test_domains = [
        "https://www.google.com",
        "https://en.wikipedia.org",
        "https://httpbin.org"
    ]
    
    logger.debug(f"Testing connectivity to {len(test_domains)} domains")
    
    for test_url in test_domains:
        try:
            connectivity = await test_network_connectivity(test_url)
            health_status["network_tests"][test_url] = "pass" if connectivity else "fail"
            logger.debug(f"Connectivity test for {test_url}: {'PASS' if connectivity else 'FAIL'}")
        except Exception as e:
            health_status["network_tests"][test_url] = f"error: {str(e)}"
            logger.error(f"Error testing connectivity to {test_url}: {str(e)}")
    
    logger.info(f"Health check completed: {health_status['status']}")
    
    # 强制刷新日志
    for handler in logging.root.handlers:
        if hasattr(handler, 'flush'):
            handler.flush()
    
    return health_status

if __name__ == "__main__":
    import uvicorn
    
    # 强制刷新日志确保启动消息被记录
    logger.info("Starting uvicorn server...")
    logger.info(f"Log file: {log_filename}")
    
    for handler in logging.root.handlers:
        if hasattr(handler, 'flush'):
            handler.flush()
    
    # 配置uvicorn日志
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
        },
        "handlers": {
            "file": {
                "formatter": "default",
                "class": "logging.FileHandler",
                "filename": log_filename,
                "mode": "a",
                "encoding": "utf-8",
            },
            "console": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "level": "DEBUG",
            "handlers": ["file", "console"],
        },
        "loggers": {
            "uvicorn": {
                "level": "DEBUG",
                "handlers": ["file", "console"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "DEBUG", 
                "handlers": ["file", "console"],
                "propagate": False,
            },
            "uvicorn.error": {
                "level": "DEBUG",
                "handlers": ["file", "console"], 
                "propagate": False,
            },
        },
    }
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        log_config=log_config,
        access_log=True
    )
