import requests
from typing import Optional, List, Dict
from config.settings import TEABLE_BASE_URL, TEABLE_API_TOKEN
from utils.error_handler import logger

HEADERS = {
    "Authorization": f"Bearer {TEABLE_API_TOKEN}",
    "Content-Type": "application/json"
}

class BaseTeableService:
    def __init__(self, table_id: str):
        self.table_id = table_id
        self.endpoint = f"{TEABLE_BASE_URL}/api/table/{table_id}/record"

    def _request(self, method: str, suffix: str = "", **kwargs) -> Optional[dict]:
        """统一请求方法，带超时和错误捕获"""
        try:
            url = f"{self.endpoint}{suffix}"
            resp = requests.request(
                method, url, headers=HEADERS, timeout=15, **kwargs
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Teable API错误 [{method} {url}]: {str(e)}", exception=e)
            return None

    def get_all(self) -> List[dict]:
        """获取所有记录（支持分页获取超过100条的数据）"""
        all_records = []
        page = 1
        page_size = 50  # 使用50而不是100，因为100是API的上限，不会返回分页信息
        
        while True:
            result = self._request(
                "GET", 
                params={"fieldKeyType": "name", "page": page, "pageSize": page_size}
            )
            if not result:
                break
            
            records = result.get("records", [])
            if not records:
                break
            
            all_records.extend(records)
            
            # 如果返回的记录数少于page_size，说明没有更多了
            if len(records) < page_size:
                break
            
            page += 1
            # 防止无限循环
            if page > 1000:
                break
        
        return all_records

    def create(self, fields: Dict) -> Optional[str]:
        """创建单条记录，返回记录ID"""
        payload = {"fieldKeyType": "name", "records": [{"fields": fields}]}
        result = self._request("POST", json=payload)
        return result["records"][0]["id"] if result and result.get("records") else None

    def update(self, record_id: str, fields: Dict) -> bool:
        """更新单条记录"""
        payload = {"fieldKeyType": "name", "record": {"fields": fields}}
        return self._request("PATCH", f"/{record_id}", json=payload) is not None

    def delete(self, record_id: str) -> bool:
        """删除单条记录"""
        return self._request("DELETE", f"/{record_id}") is not None