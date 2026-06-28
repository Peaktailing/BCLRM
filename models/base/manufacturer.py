"""生产商表数据模型

对应 SQLite 表：manufacturer

字段映射说明：
- 生产商全称 -> full_name
- 品牌名称 -> brand_name
- 官方网址 -> website
- 附件 -> attachment
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class Manufacturer:
    """生产商数据模型
    
    存储试剂生产商信息，用于溯源和质量控制。
    """
    full_name: Optional[str] = None      # 生产商全称（文本类型）
    brand_name: Optional[str] = None     # 品牌名称（文本类型，唯一标识）
    website: Optional[str] = None        # 官方网址（文本类型）
    attachment: Optional[str] = None     # 附件（文件路径）
    id: Optional[int] = None             # 自增主键