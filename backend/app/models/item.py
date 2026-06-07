"""物品/道具/装备系统模型。

对标 MuMuAINovel（无独立模型，本系统为自创增强）。
承载武器/法宝/丹药/材料/关键剧情道具，关联角色与章节。
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Text
from app.core.database import Base


class Item(Base):
    """物品/道具。"""
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    # 分类：装备/消耗/关键道具/材料/货币/其他
    category = Column(String(50), default="装备", index=True)
    # 稀有度：common(普通)/uncommon(精良)/rare(稀有)/epic(史诗)/legendary(传说)/mythic(神话)
    rarity = Column(String(20), default="common")
    item_type = Column(String(50), default="")  # 细分类型：武器/防具/法宝/丹药/功法...
    description = Column(Text, default="")
    # 属性/效果 {attack:+10, defense:+5, effect:"提升修炼速度"}
    attributes = Column(JSON, default=dict)
    # 持有者（关联角色，可空表示无主/流通中）
    owner_character_id = Column(Integer, ForeignKey("characters.id"), nullable=True)
    owner_name = Column(String(100), default="")  # 冗余角色名（便于展示）
    # 获取章节（故事时间线）
    obtained_chapter = Column(Integer, nullable=True)
    obtained_description = Column(Text, default="")  # 获取经过
    # 状态：in_use(使用中)/stored(存放)/consumed(已消耗)/lost(遗失)/destroyed(已毁)
    status = Column(String(20), default="in_use")
    # 来源：ai(自动生成)/manual(手动)/analysis(从分析提取)
    source = Column(String(20), default="manual")
    # 是否关键剧情道具（影响主线）
    is_key_item = Column(Integer, default=0)  # 0/1
    # 数量（堆叠道具）
    quantity = Column(Integer, default=1)
    structure = Column(JSON, default=dict)  # 扩展位
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "category": self.category,
            "rarity": self.rarity,
            "item_type": self.item_type,
            "description": self.description,
            "attributes": self.attributes or {},
            "owner_character_id": self.owner_character_id,
            "owner_name": self.owner_name or "",
            "obtained_chapter": self.obtained_chapter,
            "obtained_description": self.obtained_description or "",
            "status": self.status,
            "source": self.source,
            "is_key_item": self.is_key_item,
            "quantity": self.quantity,
            "structure": self.structure or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
