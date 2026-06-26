# teable_api.py 适配你的本地Teable，带异常保护
import requests
import json

# ===================== 你的配置（全部填好）=====================
# 本地Docker部署地址
TEABLE_BASE_URL = "http://localhost:3000"
TEABLE_API_TOKEN = "teable_acc18jWxz0U4AiW7njx_7qdl8Ou/t/zVTsJV/aWgMT7/3sBt+t8Uj+LkswvC6a0="

# 你的表ID（只填已确认的试剂瓶表，其他逐步加）
TABLE_IDS = {
    "reagent_bottle": "tblc71S7dbkg0VuBPhO"  # 试剂瓶信息表
}
# =============================================================

HEADERS = {
    "Authorization": f"Bearer {TEABLE_API_TOKEN}",
    "Content-Type": "application/json"
}

def get_reagent_bottles():
    """获取试剂瓶列表（安全调用，绝不闪退）"""
    try:
        url = f"{TEABLE_BASE_URL}/api/table/{TABLE_IDS['reagent_bottle']}/record?fieldKeyType=name"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("records", [])
        else:
            print(f"Teable请求失败：{resp.status_code} {resp.text}")
            return []
    except Exception as e:
        print(f"Teable连接异常：{str(e)}")
        return []