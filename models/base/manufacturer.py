"""生产商表数据模型

对应Teable表：试剂生产商表

字段映射说明：
- 名称 -> name
- 联系人 -> contact
- 电话 -> phone
- 地址 -> address
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class Manufacturer:
    """生产商数据模型
    
    存储试剂生产商信息，用于溯源和质量控制。
    """
    name: Optional[str] = None        # 生产商名称（文本类型）
    contact: Optional[str] = None     # 联系人（文本类型）
    phone: Optional[str] = None       # 电话（文本类型）
    address: Optional[str] = None     # 地址（文本类型）
    id: Optional[str] = None       # Teable内部记录ID（系统自动生成）