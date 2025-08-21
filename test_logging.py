import logging
import requests
from datetime import datetime

# 测试日志配置
log_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = f'test_log_{log_timestamp}.log'

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ],
    force=True
)

logger = logging.getLogger(__name__)

logger.info(f"Test log started - writing to {log_filename}")
logger.debug("This is a debug message")
logger.info("This is an info message")
logger.warning("This is a warning message")

# 强制刷新
for handler in logging.root.handlers:
    if hasattr(handler, 'flush'):
        handler.flush()

print(f"Test completed. Check {log_filename}")

# 测试健康检查请求
try:
    logger.info("Testing health check endpoint...")
    response = requests.get("http://localhost:8000/health", timeout=5)
    logger.info(f"Health check response: {response.status_code}")
    logger.info(f"Response content: {response.text[:200]}...")
except Exception as e:
    logger.error(f"Health check failed: {e}")

# 再次强制刷新
for handler in logging.root.handlers:
    if hasattr(handler, 'flush'):
        handler.flush()

print("Health check test completed")
