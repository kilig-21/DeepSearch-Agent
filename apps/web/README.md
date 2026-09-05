# apps/web — Orca Research 前端(Phase 1B)

Next.js 15(App Router)+ Tailwind CSS v4。逻辑正确优先,不追求美观。

## 页面

- `/` 研究页:输入问题 → 时间线(plan/search/reading/note/reflection/warning)
  → 报告区(report_delta 草稿流式 → 落库后取正式版替换);运行中可取消
- `/history` 历史报告:GET `/api/reports` 列表 → 详情渲染 → 导出 `.md`

## SSE 两路恢复(§3.4)

- 页面在、连接断:浏览器 `EventSource` 自动重连(带 Last-Event-ID),
  服务端从环形缓冲补发
- 刷新/视图丢失:重开页面按 `sessionStorage.orca.task_id` 重新订阅(不带任何
  seq 参数),服务端先发完整 snapshot 整体替换;时间线历史明细不回放,显示概要
- 终态(done/task_failed/cancelled)或显示终态的 snapshot → 主动 `close()`

Markdown 一律过 `rehype-sanitize`(禁 `img`,即禁远程图片);引用 `[n]` 渲染为
可点击链接,文末列出引用来源。

## 启动

```bash
npm install
npm run dev   # http://localhost:3000,需后端先起
```

后端:`apps/api` 下 `.venv/Scripts/python.exe -m uvicorn --factory orca.api:create_app --port 8000`

环境变量 `NEXT_PUBLIC_API_BASE` 可覆盖 API 地址(默认 `http://localhost:8000`)。
