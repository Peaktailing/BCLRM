import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import Database

db = Database()

print('=== 插入基础试剂类型数据 ===')

reagent_types = [
    ('分析纯', '分析纯试剂，用于分析实验'),
    ('化学纯', '化学纯试剂，用于一般化学实验'),
    ('优级纯', '优级纯试剂，纯度最高'),
    ('基准试剂', '基准试剂，用于标定标准溶液'),
    ('色谱纯', '色谱纯试剂，用于色谱分析'),
    ('光谱纯', '光谱纯试剂，用于光谱分析'),
    ('生化试剂', '生化试剂，用于生物化学实验'),
    ('指示剂', '化学指示剂'),
    ('标准溶液', '标准溶液'),
    ('其他', '其他类型试剂'),
]

for name, desc in reagent_types:
    try:
        db.execute_insert(
            'INSERT OR IGNORE INTO reagent_type (name, description) VALUES (?, ?)',
            (name, desc)
        )
        print('  OK:', name)
    except Exception as e:
        print('  FAIL:', name, str(e))

print('')
print('=== 插入基础存储要求数据 ===')

storage_requirements = [
    ('室温', '室温存储，15-25℃'),
    ('冷藏', '冷藏存储，2-8℃'),
    ('冷冻', '冷冻存储，-20℃以下'),
    ('避光', '避光保存'),
    ('干燥', '干燥环境保存'),
    ('防潮', '防潮保存'),
    ('通风', '通风良好环境保存'),
]

for name, desc in storage_requirements:
    try:
        db.execute_insert(
            'INSERT OR IGNORE INTO storage_requirement (name, description) VALUES (?, ?)',
            (name, desc)
        )
        print('  OK:', name)
    except Exception as e:
        print('  FAIL:', name, str(e))

print('')
print('=== 验证数据 ===')
result = db.execute_query('SELECT COUNT(*) as count FROM reagent_type')
print('试剂类型数量:', result[0]['count'])

result = db.execute_query('SELECT COUNT(*) as count FROM storage_requirement')
print('存储要求数量:', result[0]['count'])

db.close()
print('')
print('基础数据插入完成！')
