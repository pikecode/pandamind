# 2026-06-03 — 预配置 API Key 功能

> 更新日期：2026-06-03

---

## 功能概述

支持在环境变量中预配置 API Key，无需通过 Admin API 创建即可直接使用。

## 使用场景

- 自动化部署时预生成固定 Key
- 多服务间共享 API Key
- 测试环境快速配置

## 配置方法

### 1. 生成 API Key

```bash
python -c "from pandamind.services.api_keys import generate_api_key; print(generate_api_key().plaintext)"
# pmk_live_abc123_xxx
```

### 2. 写入 .env

```bash
# .env
API_KEYS="pmk_live_abc123:chat:invoke,process:invoke;pmk_live_def456:models:list"
```

**格式**：`key=scope1,scope2;key2=scope3`

### 3. 直接使用

```bash
curl -H "Authorization: Bearer pmk_live_abc123" http://localhost:8000/v1/models
```

## 实现变更

| 文件 | 变更 |
|------|------|
| `apps/server/src/pandamind/core/config.py` | 添加 `api_keys` 配置字段和 `pre_configured_api_keys` 属性 |
| `apps/server/src/pandamind/services/api_keys.py` | `authenticate_api_key` 优先检查预配置 Key |

## 优先级

预配置 Key > 数据库存储 Key

当请求到达时：
1. 先检查 `API_KEYS` 环境变量
2. 匹配成功直接返回身份
3. 匹配失败再查数据库

## 注意事项

- 预配置 Key 不存储在数据库中
- 不支持过期时间、模型限制等高级功能
- 适用于简单场景，复杂权限控制仍用 Admin API
