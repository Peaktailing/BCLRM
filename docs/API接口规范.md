# 试剂库管理系统 — 前后端 API 接口规范

> **版本：v1.0** | **日期：2026-07-04** | **维护人：项目组**
>
> 本文档定义了 Streamlit Python 后端（API Server）与 React 前端（login-frontend）之间的 RESTful API 契约，是前后端联调的唯一权威依据。
>
> 后端优先实现 Streamlit 原生页面，API 接口作为 React 前端对接的并行通道，两者共享同一套 business/ + services/ 业务逻辑层。

---

## 目录

1. [通用约定](#一通用约定)
2. [认证 (Authentication)](#二认证-authentication)
3. [试剂库存 (Reagent Inventory)](#三试剂库存-reagent-inventory)
4. [领用 (Borrow)](#四领用-borrow)
5. [归还 (Return)](#五归还-return)
6. [查询 (Query)](#六查询-query)
7. [化学品信息 (Chemical Info)](#七化学品信息-chemical-info)
8. [统计 (Statistics)](#八统计-statistics)
9. [系统设置 (Settings)](#九系统设置-settings)
10. [实验项目 (Experiment)](#十实验项目-experiment)
11. [预定单 (Reservation)](#十一预定单-reservation)
12. [采购单 (Purchase)](#十二采购单-purchase)

---

## 一、通用约定

### 1.1 基础信息

| 项目 | 说明 |
|------|------|
| 协议 | HTTP/HTTPS |
| 数据格式 | JSON（`Content-Type: application/json`） |
| 字符编码 | UTF-8 |
| 认证方式 | Session Token（Cookie）或 Bearer Token（Header） |
| 基础路径 | `http://{host}:{port}/api` |

### 1.2 请求头规范

所有请求必须携带以下请求头：

```http
Content-Type: application/json
Authorization: Bearer {token}    # 除登录接口外，其余接口均需携带
```

### 1.3 统一响应格式

#### 成功响应

```json
{
  "success": true,
  "message": "操作成功",
  "data": { ... },
  "timestamp": "2026-07-04T12:00:00+08:00"
}
```

#### 失败响应

```json
{
  "success": false,
  "message": "错误描述信息",
  "error_code": "INVALID_PARAMETER",
  "timestamp": "2026-07-04T12:00:00+08:00"
}
```

### 1.4 HTTP 状态码

| 状态码 | 含义 | 使用场景 |
|--------|------|----------|
| 200 | 成功 | 请求成功，返回数据 |
| 201 | 已创建 | POST 创建资源成功 |
| 400 | 请求参数错误 | 参数校验失败 |
| 401 | 未认证 | 未登录或 Token 过期 |
| 403 | 无权限 | 权限不足（如非管理员访问管理接口） |
| 404 | 未找到 | 资源不存在 |
| 409 | 冲突 | 数据冲突（如唯一键重复） |
| 422 | 实体错误 | 业务逻辑校验失败（如领用数量超限） |
| 500 | 服务器内部错误 | 后端异常 |

### 1.5 分页参数

涉及列表查询的接口统一使用以下分页参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码（从 1 开始） |
| `page_size` | int | 100 | 每页条数（最大 500） |

分页响应格式：

```json
{
  "success": true,
  "data": {
    "items": [ ... ],
    "total": 156,
    "page": 1,
    "page_size": 100,
    "total_pages": 2
  }
}
```

### 1.6 错误码定义

| 错误码 | 说明 |
|--------|------|
| `INVALID_PARAMETER` | 请求参数不合法 |
| `UNAUTHORIZED` | 未认证或 Token 已过期 |
| `FORBIDDEN` | 无权访问该资源 |
| `NOT_FOUND` | 请求的资源不存在 |
| `CONFLICT` | 数据冲突（唯一键重复） |
| `BUSINESS_ERROR` | 业务逻辑校验失败 |
| `INSUFFICIENT_STOCK` | 库存不足 |
| `CONTROLLED_CHEMICAL` | 管控化学品需审批 |
| `INTERNAL_ERROR` | 服务器内部错误 |

---

## 二、认证 (Authentication)

### 2.1 登录 — POST /api/auth/login

用户登录，获取认证 Token。

**请求头：**
```http
Content-Type: application/json
```

**请求体：**
```json
{
  "username": "zhangsan",
  "password": "********"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | 是 | 用户名（对应 person 表 name 字段） |
| `password` | string | 是 | 密码（预留字段，当前版本可传空字符串） |

**成功响应 (200)：**
```json
{
  "success": true,
  "message": "登录成功",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "user": {
      "id": 1,
      "name": "张三",
      "role": "管理员",
      "department": "化学系",
      "student_or_work_id": "T2024001"
    },
    "expires_in": 86400
  }
}
```

**失败响应：**
```json
// 401 — 用户名或密码错误
{
  "success": false,
  "message": "用户名或密码错误",
  "error_code": "UNAUTHORIZED"
}

// 401 — 用户不存在
{
  "success": false,
  "message": "用户不存在，请联系管理员",
  "error_code": "UNAUTHORIZED"
}
```

### 2.2 登出 — POST /api/auth/logout

用户登出，使当前 Token 失效。

**请求头：**
```http
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体：** 无

**成功响应 (200)：**
```json
{
  "success": true,
  "message": "已登出"
}
```

### 2.3 获取当前用户信息 — GET /api/auth/me

获取当前登录用户的详细信息。

**请求头：**
```http
Authorization: Bearer {token}
```

**成功响应 (200)：**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "张三",
    "role": "管理员",
    "department": "化学系",
    "phone": "13800138000",
    "student_or_work_id": "T2024001"
  }
}
```

**失败响应：**
```json
// 401 — Token 无效或过期
{
  "success": false,
  "message": "认证已过期，请重新登录",
  "error_code": "UNAUTHORIZED"
}
```

---

## 三、试剂库存 (Reagent Inventory)

### 3.1 获取试剂列表 — GET /api/reagents

分页获取所有试剂瓶信息。

**请求头：**
```http
Authorization: Bearer {token}
```

**查询参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `page` | int | 否 | 1 | 页码 |
| `page_size` | int | 否 | 100 | 每页条数 |
| `status` | string | 否 | - | 状态筛选：`borrowable`（可借）/ `borrowed`（已借出）/ `exhausted`（耗尽） |
| `keyword` | string | 否 | - | 关键词搜索（匹配编号、名称、CAS号） |

**成功响应 (200)：**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "bottle_number": "202606290001",
        "barcode": "RE202606290001",
        "reagent_name": "氯化钠",
        "cas_number": "7647-14-5",
        "remaining_quantity": 500.0,
        "specification": 500.0,
        "purity": "分析纯",
        "reagent_type": "普通固体试剂",
        "is_controlled": 0,
        "storage_requirement": "常温干燥",
        "unit_price": 25.00,
        "supplier": "国药集团",
        "production_date": "2025-06-15",
        "inbound_date": "2026/06/29 10:30",
        "unseal_date": null,
        "last_borrow_time": null,
        "last_return_time": null,
        "storage_location": "A栋301室1号柜",
        "borrowable_flag": "可借",
        "expired_flag": "正常",
        "expiry_date": "2028-06-15"
      }
    ],
    "total": 156,
    "page": 1,
    "page_size": 100,
    "total_pages": 2
  }
}
```

### 3.2 获取单个试剂瓶详情 — GET /api/reagents/{bottle_number}

**请求头：**
```http
Authorization: Bearer {token}
```

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `bottle_number` | string | 是 | 试剂瓶编号（如 `202606290001`） |

**成功响应 (200)：**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "bottle_number": "202606290001",
    "barcode": "RE202606290001",
    "reagent_name": "氯化钠",
    "cas_number": "7647-14-5",
    "remaining_quantity": 500.0,
    "specification": 500.0,
    "purity": "分析纯",
    "reagent_type": "普通固体试剂",
    "is_controlled": 0,
    "storage_requirement": "常温干燥",
    "unit_price": 25.00,
    "supplier": "国药集团",
    "production_date": "2025-06-15",
    "inbound_date": "2026/06/29 10:30",
    "unseal_date": null,
    "last_borrow_time": null,
    "last_return_time": null,
    "last_return_record_no": null,
    "storage_location": "A栋301室1号柜",
    "borrowable_flag": "可借",
    "expired_flag": "正常",
    "expiry_date": "2028-06-15",
    "borrow_history": [
      {
        "record_number": "B202606290001",
        "user": "李四",
        "borrow_time": "2026/07/01 14:30",
        "approved": true
      }
    ]
  }
}
```

**失败响应：**
```json
// 404
{
  "success": false,
  "message": "未找到该试剂瓶（编号：202606290001）",
  "error_code": "NOT_FOUND"
}
```

### 3.3 试剂入库 — POST /api/reagents

创建新的试剂瓶入库记录。

**请求头：**
```http
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体：**
```json
{
  "reagent_name": "氯化钠",
  "cas_number": "7647-14-5",
  "remaining_quantity": 500.0,
  "specification": 500.0,
  "purity": "分析纯",
  "reagent_type": "普通固体试剂",
  "unit_price": 25.00,
  "supplier": "国药集团",
  "production_date": "2025-06-15",
  "storage_location": "A栋301室1号柜",
  "storage_requirement": "常温干燥"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `reagent_name` | string | 是 | 试剂名称（必须在 chemical_info 表中存在） |
| `cas_number` | string | 是 | CAS号 |
| `remaining_quantity` | float | 是 | 剩余量（g），必须 > 0 |
| `specification` | float | 是 | 规格（g），必须 ≥ remaining_quantity |
| `purity` | string | 否 | 纯度（分析纯/化学纯/优级纯/色谱纯/光谱纯/电子纯/工业纯） |
| `reagent_type` | string | 否 | 试剂类型 |
| `unit_price` | float | 否 | 采购单价（元） |
| `supplier` | string | 否 | 供应商名称 |
| `production_date` | string | 否 | 生产日期（YYYY-MM-DD） |
| `storage_location` | string | 否 | 存储位置 |
| `storage_requirement` | string | 否 | 存储要求 |

**业务规则：**
- `reagent_name` 必须在 `chemical_info` 表中存在
- `remaining_quantity` 必须 ≤ `specification`
- `remaining_quantity` > 0 时，`borrowable_flag` 自动设为「可借」
- 入库时自动生成 `bottle_number`（格式：YYYYMMDDNNNN）和 `barcode`
- 入库时自动检测是否为管控化学品（匹配 `controlled_list` 表）

**成功响应 (201)：**
```json
{
  "success": true,
  "message": "入库成功！试剂瓶编号：202606290001，条码：RE202606290001",
  "data": {
    "bottle_number": "202606290001",
    "barcode": "RE202606290001",
    "is_controlled": false
  }
}
```

**管控化学品成功响应 (201)：**
```json
{
  "success": true,
  "message": "入库成功！试剂瓶编号：202606290002，条码：RE202606290002\n注意：该试剂为管控化学品（易制毒）",
  "data": {
    "bottle_number": "202606290002",
    "barcode": "RE202606290002",
    "is_controlled": true,
    "controlled_type": "易制毒"
  }
}
```

**失败响应：**
```json
// 422 — 试剂名称未在化学品信息表中注册
{
  "success": false,
  "message": "试剂名称「未知试剂」未在化学品信息表中注册，请先在化学品信息管理中添加",
  "error_code": "BUSINESS_ERROR"
}

// 422 — 剩余量超过规格
{
  "success": false,
  "message": "剩余量（1000.0g）超过规格（500.0g），请检查输入",
  "error_code": "INVALID_PARAMETER"
}
```

---

## 四、领用 (Borrow)

### 4.1 试剂领用 — POST /api/borrow

执行试剂领用操作，创建领用记录并更新库存。

**请求头：**
```http
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体：**
```json
{
  "bottle_number": "202606290001",
  "user": "李四",
  "borrow_quantity": 500.0
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `bottle_number` | string | 是 | 试剂瓶编号 |
| `user` | string | 是 | 领用人姓名（必须在 person 表中存在） |
| `borrow_quantity` | float | 是 | 领用数量（g），必须 > 0 |

**业务规则：**
- 试剂瓶 `borrowable_flag` 必须为「可借」
- `borrow_quantity` 必须 ≤ `remaining_quantity`
- 领用后自动更新试剂瓶剩余量和状态
- 领用后自动创建领用记录（`borrow_record` 表）
- 管控化学品领用会生成提示，但不阻塞操作（审批功能预留）

**成功响应 (200)：**
```json
{
  "success": true,
  "message": "领用成功！",
  "data": {
    "record_number": "B202607040001",
    "bottle_number": "202606290001",
    "reagent_name": "氯化钠",
    "user": "李四",
    "borrow_time": "2026/07/04 15:30",
    "remaining_after": 0.0,
    "is_controlled": false
  }
}
```

**管控化学品领用响应 (200)：**
```json
{
  "success": true,
  "message": "该试剂为管控化学品（易制毒），请及时补全审批手续",
  "data": {
    "record_number": "B202607040002",
    "bottle_number": "202606290005",
    "reagent_name": "硫酸",
    "user": "李四",
    "borrow_time": "2026/07/04 15:35",
    "remaining_after": 0.0,
    "is_controlled": true,
    "controlled_type": "易制毒"
  }
}
```

**失败响应：**
```json
// 422 — 试剂瓶不可借
{
  "success": false,
  "message": "该试剂当前状态为「已借出」，不可借出",
  "error_code": "BUSINESS_ERROR"
}

// 422 — 领用数量超限
{
  "success": false,
  "message": "领用数量（600.0g）超过剩余量（500.0g）",
  "error_code": "INSUFFICIENT_STOCK"
}

// 404 — 试剂瓶不存在
{
  "success": false,
  "message": "未找到该试剂瓶（编号：999999999999）",
  "error_code": "NOT_FOUND"
}

// 422 — 并发冲突
{
  "success": false,
  "message": "该试剂已被其他用户领用",
  "error_code": "CONFLICT"
}
```

### 4.2 获取领用历史 — GET /api/borrow/history

分页查询领用记录历史。

**请求头：**
```http
Authorization: Bearer {token}
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 100 |
| `bottle_number` | string | 否 | 按试剂瓶编号精确筛选 |
| `user` | string | 否 | 按领用人模糊筛选 |
| `start_date` | string | 否 | 起始日期（YYYY-MM-DD） |
| `end_date` | string | 否 | 结束日期（YYYY-MM-DD） |
| `is_controlled` | int | 否 | 是否管控试剂（0/1） |

**成功响应 (200)：**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "record_number": "B202607040001",
        "bottle_number": "202606290001",
        "reagent_name": "氯化钠",
        "user": "李四",
        "cas_number": "7647-14-5",
        "production_date": "2025-06-15",
        "is_controlled": 0,
        "borrow_time": "2026/07/04 15:30",
        "approver": null,
        "approved": null,
        "is_violation": 0,
        "borrow_type": "teacher",
        "linked_return_record_number": null
      }
    ],
    "total": 42,
    "page": 1,
    "page_size": 100,
    "total_pages": 1
  }
}
```

---

## 五、归还 (Return)

### 5.1 试剂归还 — POST /api/return

执行试剂归还操作，创建归还记录并更新库存状态。

**请求头：**
```http
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体：**
```json
{
  "bottle_number": "202606290001",
  "return_user": "李四",
  "remaining_quantity": 350.0
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `bottle_number` | string | 是 | 试剂瓶编号 |
| `return_user` | string | 是 | 归还人姓名 |
| `remaining_quantity` | float | 是 | 归还时剩余量（g），必须 ≥ 0 |

**业务规则：**
- 试剂瓶必须在「已借出」或「耗尽」状态
- `remaining_quantity` > 0 时，试剂瓶状态恢复为「可借」
- `remaining_quantity` == 0 时，试剂瓶状态为「耗尽」
- 自动关联最近的领用记录

**成功响应 (200)：**
```json
{
  "success": true,
  "message": "归还成功！",
  "data": {
    "return_number": "R202607040001",
    "bottle_number": "202606290001",
    "return_user": "李四",
    "return_time": "2026/07/04 16:00",
    "remaining_quantity": 350.0,
    "new_status": "可借",
    "linked_borrow_record": "B202607040001"
  }
}
```

**失败响应：**
```json
// 422 — 试剂瓶未处于借出状态
{
  "success": false,
  "message": "当前试剂瓶状态为「可借」，无需归还",
  "error_code": "BUSINESS_ERROR"
}

// 404 — 试剂瓶不存在
{
  "success": false,
  "message": "未找到该试剂瓶（编号：999999999999）",
  "error_code": "NOT_FOUND"
}
```

### 5.2 获取归还历史 — GET /api/return/history

分页查询归还记录历史。

**请求头：**
```http
Authorization: Bearer {token}
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 100 |
| `bottle_number` | string | 否 | 按试剂瓶编号精确筛选 |
| `return_user` | string | 否 | 按归还人模糊筛选 |
| `start_date` | string | 否 | 起始日期（YYYY-MM-DD） |
| `end_date` | string | 否 | 结束日期（YYYY-MM-DD） |

**成功响应 (200)：**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "return_number": "R202607040001",
        "bottle_number": "202606290001",
        "return_user": "李四",
        "return_time": "2026/07/04 16:00",
        "remaining_quantity": 350.0,
        "linked_borrow_record_number": "B202607040001",
        "last_update_time": "2026/07/04 16:00",
        "modifier": "李四"
      }
    ],
    "total": 38,
    "page": 1,
    "page_size": 100,
    "total_pages": 1
  }
}
```

---

## 六、查询 (Query)

### 6.1 多条件试剂查询 — GET /api/query/reagents

支持多条件组合查询试剂瓶信息。

**请求头：**
```http
Authorization: Bearer {token}
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `bottle_number` | string | 否 | 试剂瓶编号（精确匹配） |
| `reagent_name` | string | 否 | 试剂名称（模糊匹配，不区分大小写） |
| `cas_number` | string | 否 | CAS号（精确匹配） |
| `supplier` | string | 否 | 供应商（模糊匹配） |
| `status` | string | 否 | 状态：`borrowable` / `borrowed` / `exhausted` |
| `purity` | string | 否 | 纯度（精确匹配） |
| `reagent_type` | string | 否 | 试剂类型（模糊匹配） |
| `storage_location` | string | 否 | 存储位置（模糊匹配） |
| `is_controlled` | int | 否 | 是否管控试剂（0/1） |
| `expired_flag` | string | 否 | 过期状态：`正常` / `即将过期` / `已过期` |
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 100 |

**成功响应 (200)：**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "bottle_number": "202606290001",
        "barcode": "RE202606290001",
        "reagent_name": "氯化钠",
        "cas_number": "7647-14-5",
        "remaining_quantity": 500.0,
        "specification": 500.0,
        "purity": "分析纯",
        "reagent_type": "普通固体试剂",
        "is_controlled": 0,
        "supplier": "国药集团",
        "storage_location": "A栋301室1号柜",
        "borrowable_flag": "可借",
        "expired_flag": "正常",
        "expiry_date": "2028-06-15"
      }
    ],
    "total": 12,
    "page": 1,
    "page_size": 100,
    "total_pages": 1
  }
}
```

### 6.2 管控化学品查询 — GET /api/query/controlled

分页查询管控化学品名录。

**请求头：**
```http
Authorization: Bearer {token}
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 否 | 关键词（匹配化学品名称、别名、CAS号） |
| `dangerous_type` | string | 否 | 危化品类型（如：剧毒、易制爆、易制毒） |
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 100 |

**成功响应 (200)：**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "chemical_name": "硫酸",
        "alias": "浓硫酸",
        "cas_number": "7664-93-9",
        "dangerous_type": "易制毒"
      }
    ],
    "total": 85,
    "page": 1,
    "page_size": 100,
    "total_pages": 1
  }
}
```

> **注意**：管控化学品名录为只读数据，通过脚本导入，不提供增删改接口。

---

## 七、化学品信息 (Chemical Info)

化学品信息管理（对应 `chemical_info` 表）。

### 7.1 获取化学品列表 — GET /api/chemicals

**请求头：**
```http
Authorization: Bearer {token}
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 否 | 关键词（匹配名称、显示名称、CAS号） |
| `reagent_type` | string | 否 | 按试剂类型筛选 |
| `controlled_type` | string | 否 | 按管控类型筛选 |
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 100 |

**成功响应 (200)：**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "name": "氯化钠",
        "display_name": "食盐",
        "formula": "NaCl",
        "cas_number": "7647-14-5",
        "msds": "/attachments/msds_001.pdf",
        "reagent_type": "普通固体试剂",
        "storage_requirement": "常温干燥",
        "controlled_type": null,
        "unsealed_shelf_life": 365,
        "sealed_shelf_life": 1095
      }
    ],
    "total": 200,
    "page": 1,
    "page_size": 100,
    "total_pages": 2
  }
}
```

### 7.2 获取单个化学品 — GET /api/chemicals/{id}

**请求头：**
```http
Authorization: Bearer {token}
```

**成功响应 (200)：**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "氯化钠",
    "display_name": "食盐",
    "formula": "NaCl",
    "cas_number": "7647-14-5",
    "msds": "/attachments/msds_001.pdf",
    "reagent_type": "普通固体试剂",
    "storage_requirement": "常温干燥",
    "controlled_type": null,
    "unsealed_shelf_life": 365,
    "sealed_shelf_life": 1095
  }
}
```

### 7.3 创建化学品 — POST /api/chemicals

**请求头：**
```http
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体：**
```json
{
  "name": "氢氧化钠",
  "display_name": "烧碱",
  "formula": "NaOH",
  "cas_number": "1310-73-2",
  "reagent_type": "普通固体试剂",
  "storage_requirement": "密封干燥",
  "unsealed_shelf_life": 180,
  "sealed_shelf_life": 730
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 化学品名称（唯一） |
| `display_name` | string | 否 | 通用显示名称 |
| `formula` | string | 否 | 化学式 |
| `cas_number` | string | 是 | CAS号（唯一） |
| `reagent_type` | string | 是 | 试剂类型 |
| `storage_requirement` | string | 是 | 存储要求 |
| `unsealed_shelf_life` | int | 否 | 未启封有效时长（天） |
| `sealed_shelf_life` | int | 否 | 启封有效时长（天） |

**业务规则：**
- `name` 和 `cas_number` 必须唯一
- 创建时自动匹配 `controlled_list` 表，自动设置 `controlled_type`

**成功响应 (201)：**
```json
{
  "success": true,
  "message": "化学品添加成功！",
  "data": {
    "id": 201,
    "name": "氢氧化钠",
    "cas_number": "1310-73-2",
    "controlled_type": null
  }
}
```

**失败响应：**
```json
// 409 — 名称已存在
{
  "success": false,
  "message": "化学品名称「氢氧化钠」已存在",
  "error_code": "CONFLICT"
}

// 409 — CAS号已存在
{
  "success": false,
  "message": "CAS号「1310-73-2」已被其他记录使用",
  "error_code": "CONFLICT"
}
```

### 7.4 更新化学品 — PUT /api/chemicals/{id}

**请求头：**
```http
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体：**（所有字段可选，仅更新传入的字段）
```json
{
  "display_name": "苛性钠",
  "storage_requirement": "密封干燥避光",
  "unsealed_shelf_life": 365
}
```

**成功响应 (200)：**
```json
{
  "success": true,
  "message": "化学品更新成功！",
  "data": {
    "id": 201,
    "name": "氢氧化钠",
    "updated_fields": ["display_name", "storage_requirement", "unsealed_shelf_life"]
  }
}
```

**失败响应：**
```json
// 404
{
  "success": false,
  "message": "未找到该化学品记录",
  "error_code": "NOT_FOUND"
}

// 409 — 名称冲突
{
  "success": false,
  "message": "化学品名称已被其他记录使用",
  "error_code": "CONFLICT"
}
```

---

## 八、统计 (Statistics)

### 8.1 库存统计 — GET /api/stats/inventory

获取库存总体统计数据。

**请求头：**
```http
Authorization: Bearer {token}
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `semester` | string | 否 | 学期筛选（如 `2025-2026-2`），不传则返回全部 |

**成功响应 (200)：**
```json
{
  "success": true,
  "data": {
    "total_bottles": 156,
    "borrowable": 120,
    "borrowed": 28,
    "exhausted": 8,
    "total_quantity": 75000.5,
    "controlled_count": 15,
    "expiring_soon": 3,
    "expired": 1,
    "by_type": {
      "普通固体试剂": 80,
      "普通液体试剂": 45,
      "标准品": 20,
      "生化试剂": 11
    },
    "by_location": {
      "A栋301室1号柜": 60,
      "A栋301室2号柜": 50,
      "危化品存储柜1": 15,
      "冰箱1号": 31
    },
    "by_supplier": {
      "国药集团": 55,
      "Sigma-Aldrich": 30,
      "阿拉丁": 40,
      "麦克林": 31
    }
  }
}
```

### 8.2 领用统计 — GET /api/stats/borrow

获取领用统计数据。

**请求头：**
```http
Authorization: Bearer {token}
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `semester` | string | 否 | 学期筛选（如 `2025-2026-2`） |
| `start_date` | string | 否 | 起始日期（YYYY-MM-DD） |
| `end_date` | string | 否 | 结束日期（YYYY-MM-DD） |

**成功响应 (200)：**
```json
{
  "success": true,
  "data": {
    "total_borrows": 342,
    "total_returns": 310,
    "current_borrowed": 28,
    "controlled_borrows": 42,
    "by_user": {
      "李四": 58,
      "王五": 45,
      "张三": 38,
      "赵六": 32,
      "钱七": 28
    },
    "by_month": {
      "2026-01": 28,
      "2026-02": 22,
      "2026-03": 35,
      "2026-04": 30,
      "2026-05": 32,
      "2026-06": 25,
      "2026-07": 10
    }
  }
}
```

---

## 九、系统设置 (Settings)

### 9.1 数据库表查看（管理员）— GET /api/settings/tables

查看所有数据库表的基本信息。**仅管理员可访问。**

**请求头：**
```http
Authorization: Bearer {token}
```

**成功响应 (200)：**
```json
{
  "success": true,
  "data": {
    "databases": {
      "main.db": {
        "path": "db/main.db",
        "tables": [
          {"name": "person", "row_count": 50, "description": "人员信息表"},
          {"name": "reagent_bottle", "row_count": 156, "description": "试剂瓶信息表"},
          {"name": "borrow_record", "row_count": 342, "description": "领用记录表"},
          {"name": "return_record", "row_count": 310, "description": "归还记录表"},
          {"name": "chemical_info", "row_count": 200, "description": "化学品信息表"},
          {"name": "controlled_list", "row_count": 85, "description": "管控化学品名录"},
          {"name": "supplier", "row_count": 25, "description": "供应商表"},
          {"name": "storage_location", "row_count": 12, "description": "存储位置表"},
          {"name": "storage_requirement", "row_count": 8, "description": "存储要求表"},
          {"name": "reagent_type", "row_count": 6, "description": "试剂类型表"},
          {"name": "manufacturer", "row_count": 15, "description": "生产商表"},
          {"name": "consumable", "row_count": 0, "description": "耗材信息表"},
          {"name": "experiment_project", "row_count": 5, "description": "实验项目表"},
          {"name": "experiment_reagent_usage", "row_count": 30, "description": "实验试剂使用记录表"},
          {"name": "reservation_order", "row_count": 3, "description": "预定单表"},
          {"name": "purchase_order", "row_count": 2, "description": "采购单表"}
        ]
      },
      "archive_cold.db": {
        "path": "db/archive_cold.db",
        "tables": [
          {"name": "archived_reagent_bottle", "row_count": 120, "description": "归档试剂瓶"},
          {"name": "archived_borrow_record", "row_count": 200, "description": "归档领用记录"},
          {"name": "archived_return_record", "row_count": 180, "description": "归档归还记录"}
        ]
      },
      "attach_cold.db": {
        "path": "db/attach_cold.db",
        "tables": [
          {"name": "attachment", "row_count": 45, "description": "附件索引"}
        ]
      },
      "operation_log.db": {
        "path": "db/operation_log.db",
        "tables": [
          {"name": "operation_log", "row_count": 1523, "description": "操作审计日志"}
        ]
      }
    }
  }
}
```

**失败响应：**
```json
// 403 — 非管理员
{
  "success": false,
  "message": "仅管理员可查看数据库表信息",
  "error_code": "FORBIDDEN"
}
```

---

## 十、实验项目 (Experiment)

实验项目及试剂使用记录管理（对应 `experiment_project` 和 `experiment_reagent_usage` 表）。

### 10.1 获取实验项目列表 — GET /api/experiments

**请求头：**
```http
Authorization: Bearer {token}
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `semester` | string | 否 | 按学期筛选（如 `2025-2026-2`） |
| `teacher` | string | 否 | 按负责教师筛选 |
| `keyword` | string | 否 | 关键词（匹配项目名称） |
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 100 |

**成功响应 (200)：**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "project_name": "有机合成实验",
        "semester": "2025-2026-2",
        "teacher": "张三",
        "description": "本实验为本科有机化学基础实验",
        "created_at": "2026-06-01T10:00:00",
        "reagent_count": 5
      }
    ],
    "total": 5,
    "page": 1,
    "page_size": 100,
    "total_pages": 1
  }
}
```

### 10.2 获取单个实验项目 — GET /api/experiments/{id}

**请求头：**
```http
Authorization: Bearer {token}
```

**成功响应 (200)：**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "project_name": "有机合成实验",
    "semester": "2025-2026-2",
    "teacher": "张三",
    "description": "本实验为本科有机化学基础实验",
    "created_at": "2026-06-01T10:00:00",
    "updated_at": "2026-06-15T14:30:00",
    "reagent_usages": [
      {
        "id": 1,
        "reagent_name": "乙酸乙酯",
        "cas_number": "141-78-6",
        "usage_quantity": 250.0,
        "usage_date": "2026-06-10"
      }
    ]
  }
}
```

### 10.3 创建实验项目 — POST /api/experiments

**请求头：**
```http
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体：**
```json
{
  "project_name": "有机合成实验",
  "semester": "2025-2026-2",
  "teacher": "张三",
  "description": "本实验为本科有机化学基础实验"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `project_name` | string | 是 | 实验项目名称 |
| `semester` | string | 否 | 学期（格式：YYYY-YYYY-N） |
| `teacher` | string | 否 | 负责教师 |
| `description` | string | 否 | 项目描述 |

**成功响应 (201)：**
```json
{
  "success": true,
  "message": "实验项目创建成功！",
  "data": {
    "id": 6,
    "project_name": "有机合成实验",
    "semester": "2025-2026-2"
  }
}
```

### 10.4 更新实验项目 — PUT /api/experiments/{id}

**请求头：**
```http
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体：**（所有字段可选）
```json
{
  "semester": "2025-2026-2",
  "teacher": "李四",
  "description": "更新后的实验描述"
}
```

**成功响应 (200)：**
```json
{
  "success": true,
  "message": "实验项目更新成功！",
  "data": {
    "id": 6,
    "project_name": "有机合成实验",
    "updated_fields": ["semester", "teacher", "description"]
  }
}
```

### 10.5 删除实验项目 — DELETE /api/experiments/{id}

**请求头：**
```http
Authorization: Bearer {token}
```

**成功响应 (200)：**
```json
{
  "success": true,
  "message": "实验项目已删除"
}
```

### 10.6 添加实验试剂使用记录 — POST /api/experiments/{id}/reagents

**请求头：**
```http
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体：**
```json
{
  "reagent_name": "乙酸乙酯",
  "cas_number": "141-78-6",
  "usage_quantity": 250.0,
  "usage_date": "2026-06-10"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `reagent_name` | string | 是 | 试剂名称 |
| `cas_number` | string | 否 | CAS号 |
| `usage_quantity` | float | 是 | 使用量（g） |
| `usage_date` | string | 是 | 使用日期（YYYY-MM-DD） |

**成功响应 (201)：**
```json
{
  "success": true,
  "message": "试剂使用记录添加成功！",
  "data": {
    "id": 31,
    "project_id": 1,
    "reagent_name": "乙酸乙酯",
    "usage_quantity": 250.0
  }
}
```

---

## 十一、预定单 (Reservation)

预定单管理（对应 `reservation_order` 表）。

### 11.1 获取预定单列表 — GET /api/reservations

**请求头：**
```http
Authorization: Bearer {token}
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `semester` | string | 否 | 按学期筛选 |
| `status` | string | 否 | 按状态筛选：`pending` / `approved` / `rejected` / `fulfilled` |
| `applicant` | string | 否 | 按申请人筛选 |
| `keyword` | string | 否 | 关键词（匹配试剂名称、编号） |
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 100 |

**成功响应 (200)：**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "order_number": "RES20260701001",
        "semester": "2025-2026-2",
        "reagent_name": "硫酸铜",
        "cas_number": "7758-99-8",
        "quantity": 500.0,
        "unit": "g",
        "applicant": "张三",
        "status": "pending",
        "created_at": "2026-07-01T09:00:00",
        "updated_at": "2026-07-01T09:00:00"
      }
    ],
    "total": 3,
    "page": 1,
    "page_size": 100,
    "total_pages": 1
  }
}
```

### 11.2 创建预定单 — POST /api/reservations

**请求头：**
```http
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体：**
```json
{
  "semester": "2025-2026-2",
  "reagent_name": "硫酸铜",
  "cas_number": "7758-99-8",
  "quantity": 500.0,
  "unit": "g",
  "applicant": "张三"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `semester` | string | 否 | 学期 |
| `reagent_name` | string | 是 | 试剂名称 |
| `cas_number` | string | 否 | CAS号 |
| `quantity` | float | 是 | 预定数量 |
| `unit` | string | 否 | 单位（默认 `g`） |
| `applicant` | string | 是 | 申请人 |

**业务规则：**
- 创建时自动生成 `order_number`（格式：RES + YYYYMMDD + NNNN）
- 初始状态为 `pending`

**成功响应 (201)：**
```json
{
  "success": true,
  "message": "预定单创建成功！",
  "data": {
    "id": 4,
    "order_number": "RES20260704001",
    "status": "pending"
  }
}
```

### 11.3 更新预定单 — PUT /api/reservations/{id}

**请求头：**
```http
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体：**（所有字段可选）
```json
{
  "status": "approved",
  "quantity": 600.0
}
```

**成功响应 (200)：**
```json
{
  "success": true,
  "message": "预定单更新成功！",
  "data": {
    "id": 4,
    "order_number": "RES20260704001",
    "status": "approved"
  }
}
```

### 11.4 删除预定单 — DELETE /api/reservations/{id}

**请求头：**
```http
Authorization: Bearer {token}
```

**成功响应 (200)：**
```json
{
  "success": true,
  "message": "预定单已删除"
}
```

---

## 十二、采购单 (Purchase)

采购单管理（对应 `purchase_order` 表）。

### 12.1 获取采购单列表 — GET /api/purchases

**请求头：**
```http
Authorization: Bearer {token}
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `status` | string | 否 | 按状态筛选：`pending` / `ordered` / `received` / `cancelled` |
| `supplier` | string | 否 | 按供应商筛选 |
| `keyword` | string | 否 | 关键词（匹配试剂名称、编号） |
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 100 |

**成功响应 (200)：**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "order_number": "PUR20260702001",
        "reservation_order_id": 1,
        "reagent_name": "硫酸铜",
        "cas_number": "7758-99-8",
        "order_quantity": 500.0,
        "unit_price": 35.00,
        "supplier": "国药集团",
        "status": "pending",
        "created_at": "2026-07-02T10:00:00",
        "updated_at": "2026-07-02T10:00:00"
      }
    ],
    "total": 2,
    "page": 1,
    "page_size": 100,
    "total_pages": 1
  }
}
```

### 12.2 创建采购单 — POST /api/purchases

**请求头：**
```http
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体：**
```json
{
  "reservation_order_id": 1,
  "reagent_name": "硫酸铜",
  "cas_number": "7758-99-8",
  "order_quantity": 500.0,
  "unit_price": 35.00,
  "supplier": "国药集团"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `reservation_order_id` | int | 否 | 关联的预定单 ID |
| `reagent_name` | string | 是 | 试剂名称 |
| `cas_number` | string | 否 | CAS号 |
| `order_quantity` | float | 是 | 采购数量 |
| `unit_price` | float | 否 | 单价（元） |
| `supplier` | string | 否 | 供应商 |

**业务规则：**
- 创建时自动生成 `order_number`（格式：PUR + YYYYMMDD + NNNN）
- 初始状态为 `pending`
- 可关联预定单（`reservation_order_id`）

**成功响应 (201)：**
```json
{
  "success": true,
  "message": "采购单创建成功！",
  "data": {
    "id": 3,
    "order_number": "PUR20260704001",
    "status": "pending"
  }
}
```

### 12.3 更新采购单 — PUT /api/purchases/{id}

**请求头：**
```http
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体：**（所有字段可选）
```json
{
  "status": "ordered",
  "unit_price": 38.00,
  "supplier": "阿拉丁"
}
```

**成功响应 (200)：**
```json
{
  "success": true,
  "message": "采购单更新成功！",
  "data": {
    "id": 3,
    "order_number": "PUR20260704001",
    "status": "ordered"
  }
}
```

### 12.4 删除采购单 — DELETE /api/purchases/{id}

**请求头：**
```http
Authorization: Bearer {token}
```

**成功响应 (200)：**
```json
{
  "success": true,
  "message": "采购单已删除"
}
```

---

## 附录 A：数据模型速查表

### 主库 (main.db) — 16 张表

| 序号 | 表名 | 分类 | 说明 | 主键 |
|------|------|------|------|------|
| 1 | `person` | 基础信息 | 人员信息表 | `name` (UNIQUE) |
| 2 | `storage_location` | 基础信息 | 存储位置表 | `name` (UNIQUE) |
| 3 | `storage_requirement` | 基础信息 | 存储要求表 | `name` (UNIQUE) |
| 4 | `reagent_type` | 基础信息 | 试剂类型表 | `name` (UNIQUE) |
| 5 | `supplier` | 基础信息 | 供应商表 | `name` (UNIQUE) |
| 6 | `manufacturer` | 基础信息 | 生产商表 | `brand_name` (UNIQUE) |
| 7 | `controlled_list` | 基础信息 | 管控化学品名录 | `(chemical_name, cas_number)` (UNIQUE) |
| 8 | `chemical_info` | 基础信息 | 化学品信息表 | `id` |
| 9 | `reagent_bottle` | 核心业务 | 试剂瓶信息表（系统主表） | `bottle_number` (UNIQUE) |
| 10 | `borrow_record` | 核心业务 | 领用记录表 | `record_number` (UNIQUE) |
| 11 | `return_record` | 核心业务 | 归还记录表 | `return_number` (UNIQUE) |
| 12 | `consumable` | 耗材 | 耗材信息表 | `consumable_number` (UNIQUE) |
| 13 | `experiment_project` | 扩展 | 实验项目表 | `id` |
| 14 | `experiment_reagent_usage` | 扩展 | 实验试剂使用记录表 | `id` |
| 15 | `reservation_order` | 扩展 | 预定单表 | `order_number` (UNIQUE) |
| 16 | `purchase_order` | 扩展 | 采购单表 | `order_number` (UNIQUE) |

### 归档库 (archive_cold.db) — 3 张表

| 表名 | 说明 |
|------|------|
| `archived_reagent_bottle` | 归档试剂瓶（过期数据） |
| `archived_borrow_record` | 归档领用记录 |
| `archived_return_record` | 归档归还记录 |

### 附件库 (attach_cold.db) — 1 张表

| 表名 | 说明 |
|------|------|
| `attachment` | 附件索引（文件名、路径、关联表、关联ID） |

### 日志库 (operation_log.db) — 1 张表

| 表名 | 说明 |
|------|------|
| `operation_log` | 操作审计日志（纯追加写入） |

---

## 附录 B：接口清单速查

| 方法 | URL | 说明 |
|------|-----|------|
| `POST` | `/api/auth/login` | 用户登录 |
| `POST` | `/api/auth/logout` | 用户登出 |
| `GET` | `/api/auth/me` | 获取当前用户信息 |
| `GET` | `/api/reagents` | 获取试剂列表 |
| `GET` | `/api/reagents/{bottle_number}` | 获取单个试剂瓶详情 |
| `POST` | `/api/reagents` | 试剂入库 |
| `POST` | `/api/borrow` | 试剂领用 |
| `GET` | `/api/borrow/history` | 领用历史查询 |
| `POST` | `/api/return` | 试剂归还 |
| `GET` | `/api/return/history` | 归还历史查询 |
| `GET` | `/api/query/reagents` | 多条件试剂查询 |
| `GET` | `/api/query/controlled` | 管控化学品查询 |
| `GET` | `/api/chemicals` | 化学品列表 |
| `GET` | `/api/chemicals/{id}` | 单个化学品详情 |
| `POST` | `/api/chemicals` | 创建化学品 |
| `PUT` | `/api/chemicals/{id}` | 更新化学品 |
| `GET` | `/api/stats/inventory` | 库存统计 |
| `GET` | `/api/stats/borrow` | 领用统计 |
| `GET` | `/api/settings/tables` | 数据库表查看（管理员） |
| `GET` | `/api/experiments` | 实验项目列表 |
| `GET` | `/api/experiments/{id}` | 单个实验项目 |
| `POST` | `/api/experiments` | 创建实验项目 |
| `PUT` | `/api/experiments/{id}` | 更新实验项目 |
| `DELETE` | `/api/experiments/{id}` | 删除实验项目 |
| `POST` | `/api/experiments/{id}/reagents` | 添加实验试剂使用记录 |
| `GET` | `/api/reservations` | 预定单列表 |
| `POST` | `/api/reservations` | 创建预定单 |
| `PUT` | `/api/reservations/{id}` | 更新预定单 |
| `DELETE` | `/api/reservations/{id}` | 删除预定单 |
| `GET` | `/api/purchases` | 采购单列表 |
| `POST` | `/api/purchases` | 创建采购单 |
| `PUT` | `/api/purchases/{id}` | 更新采购单 |
| `DELETE` | `/api/purchases/{id}` | 删除采购单 |