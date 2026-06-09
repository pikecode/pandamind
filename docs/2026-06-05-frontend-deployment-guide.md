# 前端部署到服务器流程

> 文档生成时间：2026-06-05
> 目标服务器：192.168.1.206

---

## 问题总结

### 1. 静态文件 mount 覆盖 API 路由

**问题**：`app.mount("/", StaticFiles(...))` 会拦截所有请求，导致 API 路由 404。

**解决**：把 `StaticFiles` mount 到 `/app` 子路径，API 路由保持 `/api/v1/...`。

```python
# main.py
app.mount("/app", StaticFiles(directory="dist", html=True), name="static")
app.include_router(api_router, prefix="/api")
```

### 2. 前端资源路径不匹配

**问题**：Vite build 后资源路径是 `/assets/xxx`，但服务器上 `StaticFiles` mount 在 `/app`，导致资源 404。

**解决**：Vite config 加 `base: '/app/'`：

```typescript
// vite.config.ts
export default defineConfig({
  base: '/app/',
  // ...
});
```

### 3. 前端 API 路径硬编码

**问题**：前端代码里直接写死 `/v1/...`，但服务器上 API 前缀是 `/api/v1/...`。

**解决**：
- `api.ts` 里 `BASE = '/api'`
- 所有 `fetch('/v1/...')` 改成 `fetch('/api/v1/...')`

### 4. SSH 命令链失败

**问题**：多命令用 `;` 或 `&&` 连接时，SSH 返回 exit code 255。

**解决**：分步执行，每条命令单独一个 SSH 连接。

---

## 部署流程

### Step 1: 本地构建

```bash
cd apps/web

# 确认 vite.config.ts 有 base: '/app/'
cat vite.config.ts

# 确认 api.ts 有 BASE = '/api'
cat src/lib/api.ts | grep "const BASE"

# 检查没有直接 fetch('/v1/...') 的硬编码
grep -rn "fetch('/v1" src/

# Build
npm run build
```

### Step 2: 上传 dist 到服务器

```bash
# 打包
tar czf /tmp/pandamind-web.tar.gz -C dist .

# 上传
sshpass -p 'fs@202103' scp -o StrictHostKeyChecking=no \
  /tmp/pandamind-web.tar.gz \
  opsuser@192.168.1.206:/tmp/

# 解压（SSH 分步执行）
sshpass -p 'fs@202103' ssh -o StrictHostKeyChecking=no opsuser@192.168.1.206 \
  "tar xzf /tmp/pandamind-web.tar.gz -C /home/opsuser/pandamind/apps/web/dist"
```

### Step 3: 更新后端代码

```bash
# 上传 main.py（含 StaticFiles mount）
sshpass -p 'fs@202103' scp -o StrictHostKeyChecking=no \
  apps/server/src/pandamind/main.py \
  opsuser@192.168.1.206:/home/opsuser/pandamind/apps/server/src/pandamind/main.py
```

### Step 4: 重启服务

```bash
# Kill uvicorn（分步执行）
sshpass -p 'fs@202103' ssh -o StrictHostKeyChecking=no opsuser@192.168.1.206 \
  "pkill -9 -f uvicorn"

# 启动 uvicorn（分步执行）
sshpass -p 'fs@202103' ssh -o StrictHostKeyChecking=no opsuser@192.168.1.206 \
  "cd /home/opsuser/pandamind/apps/server && nohup .venv/bin/uvicorn pandamind.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &"
```

### Step 5: 验证

```bash
# 前端
curl -s http://192.168.1.206:8000/app/ | head -5

# API
curl -s http://192.168.1.206:8000/api/v1/models | head -5
curl -s http://192.168.1.206:8000/api/v1/auth/login -X POST -H "Content-Type: application/json" -d '{}'
```

---

## 关键配置

### vite.config.ts

```typescript
export default defineConfig({
  plugins: [react()],
  base: '/app/',  // 关键：资源路径前缀
  server: {
    port: 5173,
    proxy: {
      '/v1': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
});
```

### api.ts

```typescript
const BASE = '/api';  // 关键：API 前缀

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path, {  // /api + /v1/... = /api/v1/...
    method: 'GET',
    headers: authHeaders(),
  });
  return handle<T>(res);
}
```

### main.py

```python
# Static files mount 到 /app
_STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "web" / "dist"
if _STATIC_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")

# API 路由加 /api 前缀
app.include_router(api_router, prefix="/api")
```

---

## 访问地址

| 服务 | URL |
|------|-----|
| 前端 | `http://192.168.1.206:8000/app/` |
| API | `http://192.168.1.206:8000/api/v1/...` |
| Health | `http://192.168.1.206:8000/health` |

---

## 防火墙

```bash
# 开放端口（root 执行）
firewall-cmd --add-port=8000/tcp --permanent
firewall-cmd --add-port=3000/tcp --permanent
firewall-cmd --reload
firewall-cmd --list-ports
```

---

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `404 Not Found` | StaticFiles 覆盖 API 路由 | mount 到 `/app` 而非 `/` |
| `404 assets/xxx` | 资源路径前缀不匹配 | vite.config.ts 加 `base: '/app/'` |
| `404 /v1/xxx` | API 路径缺少 `/api` 前缀 | `BASE = '/api'` |
| `exit code 255` | SSH 命令链失败 | 分步执行 |
| `exit code 7` | 端口未开放 | firewall-cmd 开放端口 |
