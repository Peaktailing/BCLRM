"""数据库连接测试脚本"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, '/workspace')

def test_database_connection():
    """测试数据库连接和初始化"""
    print("=== 数据库连接测试 ===")
    
    try:
        # 1. 导入数据库模块
        from db.database import Database
        print("✓ Database 模块导入成功")
        
        # 2. 初始化数据库实例
        db = Database()
        print(f"✓ Database 实例创建成功，路径: {db.db_path}")
        
        # 3. 测试连接
        conn = db.connection
        print("✓ 数据库连接建立成功")
        
        # 4. 测试基本查询
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"✓ 数据库查询成功，发现 {len(tables)} 个表")
        
        if tables:
            table_names = [t[0] for t in tables]
            print(f"  表列表: {', '.join(table_names[:5])}{'...' if len(table_names) > 5 else ''}")
        
        # 5. 测试初始化表结构
        db.init_tables()
        print("✓ 数据库表结构初始化成功")
        
        # 6. 再次查询确认表已创建
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables_after = cursor.fetchall()
        print(f"✓ 初始化后共有 {len(tables_after)} 个表")
        
        return True
        
    except Exception as e:
        print(f"✗ 数据库测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_service_initialization():
    """测试关键服务的初始化"""
    print("\n=== 服务初始化测试 ===")
    
    services = [
        ("business.expiry_service", "expiry_service"),
        ("business.return_service", "return_service"),
        ("business.query_service", "query_service"),
        ("business.borrow_service", "borrow_service"),
        ("business.inventory_service", "inventory_service"),
    ]
    
    success_count = 0
    for module_name, service_name in services:
        try:
            module = __import__(module_name, fromlist=[service_name])
            service = getattr(module, service_name)
            print(f"✓ {service_name} 初始化成功")
            success_count += 1
        except Exception as e:
            print(f"✗ {service_name} 初始化失败: {e}")
    
    print(f"\n服务初始化: {success_count}/{len(services)} 成功")
    return success_count == len(services)

if __name__ == "__main__":
    db_ok = test_database_connection()
    services_ok = test_service_initialization()
    
    print("\n" + "="*50)
    if db_ok and services_ok:
        print("✓ 所有验证通过！")
        sys.exit(0)
    else:
        print("✗ 部分验证失败")
        sys.exit(1)
