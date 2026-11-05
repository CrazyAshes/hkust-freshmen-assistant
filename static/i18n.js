"use strict";
/* UI strings. Add a key to BOTH languages; t(key, {vars}) falls back to zh, then to the key itself. */
const I18N = {
  zh: {
    "brand.tag": "只读问答 Demo",
    "welcome.title": "你好，HKUST 新生", "welcome.sub": "宿舍、餐饮、打印、Wi-Fi、体育设施、校园指南，随便问。每个回答都附官方来源，并提供中英双语。",
    "trace.title": "查看思考过程",
    "tab.chat": "问答", "tab.kb": "知识库", "tab.settings": "模型设置", "tab.log": "测试日志",
    "lang.switch": "English",
    "status.model": "模型: {model}", "status.nokey": "未填 API Key：仅检索模式", "status.build": "服务启动 {build}",
    "status.oldbuild": "旧版本(请重启服务)",

    "chat.emptyWarn": "知识库目前是空的。请先到「知识库」导入资料，否则系统会如实回答“无法确认”。",
    "chat.catAll": "全部主题", "chat.catTitle": "限定主题",
    "chat.placeholder": "输入问题，中英文均可，例如：打印额度是多少？",
    "chat.send": "发送",
    "chat.hint": "只读助手：不会替你预约、付款或提交申请。关键信息请以官方页面为准。",
    "chat.loading": "检索并生成中…", "chat.error": "出错了：{msg}",
    "examples": ["打印额度是多少？", "How do I connect to campus Wi-Fi?", "本科新生如何申请宿舍？", "体育馆的开放时间是什么？", "帮我预约羽毛球场", "附近有什么吃饭的地方？"],

    "trace.intent": "识别：{v}", "trace.categories": "主题：{v}", "trace.queries": "检索词：{v}", "trace.standalone": "理解为：{v}",
    "trace.retried": "首轮结果不足，已扩大到全部主题重试", "trace.hits": "命中 {n} 段",
    "trace.planError": "规划步骤失败，已退回普通检索（{v}）",
    "trace.nokey": "未填 API Key，智能体规划步骤未启用（仅检索）",
    "trace.split": "拆成子问题：{v}", "trace.retryQueries": "换词重试：{v}", "trace.retryReason": "原因：{v}",
    "trace.quality.partial": "资料只覆盖了部分问题", "trace.quality.poor": "资料不足以回答", "trace.quality.none": "没有找到资料",
    "trace.missing": "未找到：{v}", "trace.assumption": "说明：{v}",
    "intent.campus_question": "校园问题", "intent.chitchat": "闲聊", "intent.out_of_scope": "范围外",
    "intent.action_request": "代办请求", "intent.unclear": "不明确",
    "flag.action": "越界请求", "flag.medical": "医疗", "flag.payment": "支付", "flag.injection": "提示词注入",
    "src.badInvalid": "引用编号 {v} 无对应来源，请核对",
    "src.official": "官方", "src.student": "学生经验", "src.effective": "生效 {d}", "src.fetched": "抓取于 {d}",

    "cat.Hall": "宿舍", "cat.Dining": "餐饮", "cat.Printing": "打印", "cat.WiFi": "Wi-Fi / 网络", "cat.Sports": "体育",
    "cat.General": "校园指南", "cat.Map": "地图", "cat.Events": "活动",

    "kb.upload.title": "上传文件",
    "kb.upload.hint": "支持 .md .txt .docx .pdf .html。可在文件开头写 title / category / source_url / publisher / effective_date（每行一项，空行结束）。",
    "kb.url.ph": "来源链接 (source_url)，可选", "kb.pub.ph": "发布单位，例如 HKUST ITSO", "kb.date.ph": "生效日期 (如注明)，可选",
    "kb.fromUrl.title": "从链接导入",
    "kb.fromUrl.hint": "会抓取网页正文并清理导航。微信/腾讯文档/电子书会提示“需人工导出”，不会把链接当正文。",
    "kb.fromUrl.btn": "抓取并入库",
    "kb.paste.title": "粘贴正文", "kb.paste.titlePh": "标题", "kb.paste.bodyPh": "粘贴已核对的正文...", "kb.paste.btn": "入库",
    "kb.links.title": "链接清单（来自 Data.docx）",
    "kb.links.hint": "逐条抓取；失败的会标记为需人工导出。也可粘贴任意含链接的文本：",
    "kb.links.ph": "粘贴含链接的文本，点击“识别链接”", "kb.links.parse": "识别链接", "kb.links.fetchAll": "全部抓取",
    "kb.th.topic": "主题", "kb.th.name": "名称", "kb.th.status": "状态", "kb.th.title": "标题", "kb.th.type": "类型",
    "kb.th.chunks": "片段", "kb.th.date": "日期",
    "kb.docs.title": "已入库资料", "kb.stats": "· {d} 份 / {c} 片段 / {n} 字",
    "kb.pending": "待抓取", "kb.fetching": "抓取中…", "kb.fetchBtn": "抓取", "kb.delete": "删除",
    "kb.confirmDelete": "确定从知识库删除这份资料？",
    "kb.dup": "已存在，跳过", "kb.chunksAdded": "{n} 个片段已入库", "kb.fetchOk": "成功：{chars} 字 → {n} 个片段",
    "kb.manual": "需人工导出：",

    "set.title": "模型设置", "set.preset": "服务商预设",
    "set.preset.hkust": "HKUST 赞助额度（AISC1000）", "set.preset.openai": "OpenAI 官方", "set.preset.custom": "自定义（OpenAI 兼容接口）",
    "set.note.hkust": "HKUST 赞助额度仅限 AISC1000 课程作业使用。Key 在 https://hkust.developer.azure-api.net/ 登录后订阅 “HKUST GenAI (AISC1000 Dify)” 获取，请勿分享给他人。",
    "set.note.openai": "需要 OpenAI API 平台创建的 Key（不是 ChatGPT 登录凭证）。",
    "set.note.custom": "填写任意 OpenAI 兼容的 Base URL 和模型名称。",
    "set.model": "模型名称", "set.modelPh": "以你账号可用的模型为准",
    "set.agent": "智能体模式（先理解问题、自动分类并规划检索；需要 API Key，关闭则退回普通检索）",
    "set.remember": "仅在本浏览器标签页会话内记住 Key（关闭标签页即清除）",
    "set.test": "测试连接", "set.clear": "清除 Key", "set.testing": "测试中...", "set.cleared": "已清除。",
    "set.ok": "连接成功：{reply}",
    "set.privacy": "Key 仅随每次请求发给本机后端，再转发给所填的 API 地址；不写入数据库和日志。提问和检索到的资料片段会发送给该服务商，请勿导入敏感资料。未填 Key 时只做检索。",

    "log.title": "问答日志（最近 200 条）", "log.export": "导出 CSV",
    "log.th.time": "时间", "log.th.question": "问题", "log.th.mode": "模式", "log.th.flags": "标记", "log.th.ms": "耗时", "log.th.sources": "来源",
  },

  en: {
    "brand.tag": "Read-only Q&A demo",
    "welcome.title": "Hi, HKUST freshman", "welcome.sub": "Halls, dining, printing, Wi-Fi, sports, campus guides: ask anything. Every answer comes with official sources, in Chinese and English.",
    "trace.title": "How I got this",
    "tab.chat": "Chat", "tab.kb": "Knowledge base", "tab.settings": "Model settings", "tab.log": "Test log",
    "lang.switch": "中文",
    "status.model": "Model: {model}", "status.nokey": "No API key: retrieval-only mode", "status.build": "server started {build}",
    "status.oldbuild": "old version (restart the server)",

    "chat.emptyWarn": "The knowledge base is empty. Import material in the Knowledge base tab first; otherwise the assistant will honestly say it cannot confirm.",
    "chat.catAll": "All topics", "chat.catTitle": "Limit to a topic",
    "chat.placeholder": "Ask in English or Chinese, e.g. How do I connect to campus Wi-Fi?",
    "chat.send": "Send",
    "chat.hint": "Read-only assistant: it will not book, pay or submit anything for you. Always check key details on the official page.",
    "chat.loading": "Searching and generating…", "chat.error": "Something went wrong: {msg}",
    "examples": ["How do I connect to campus Wi-Fi?", "How much is the printing quota?", "How do undergraduate freshmen apply for hall?", "What are the sports hall opening hours?", "Book a badminton court for me", "Where can I eat nearby?"],

    "trace.intent": "Understood as: {v}", "trace.categories": "Topics: {v}", "trace.queries": "Search terms: {v}", "trace.standalone": "Rephrased: {v}",
    "trace.retried": "Too few results, retried across all topics", "trace.hits": "{n} passages found",
    "trace.planError": "Planning step failed, fell back to plain retrieval ({v})",
    "trace.nokey": "No API key: the agent planning step is off (retrieval only)",
    "trace.split": "Split into: {v}", "trace.retryQueries": "Retried with: {v}", "trace.retryReason": "Why: {v}",
    "trace.quality.partial": "Sources cover only part of the question", "trace.quality.poor": "Sources are not enough to answer", "trace.quality.none": "Nothing found",
    "trace.missing": "Not found: {v}", "trace.assumption": "Note: {v}",
    "intent.campus_question": "campus question", "intent.chitchat": "chit-chat", "intent.out_of_scope": "out of scope",
    "intent.action_request": "action request", "intent.unclear": "unclear",
    "flag.action": "action request", "flag.medical": "medical", "flag.payment": "payment", "flag.injection": "prompt injection",
    "src.badInvalid": "Citation(s) {v} have no matching source, please check",
    "src.official": "Official", "src.student": "Student experience", "src.effective": "Effective {d}", "src.fetched": "Fetched {d}",

    "cat.Hall": "Hall", "cat.Dining": "Dining", "cat.Printing": "Printing", "cat.WiFi": "Wi-Fi / IT", "cat.Sports": "Sports",
    "cat.General": "General guide", "cat.Map": "Map", "cat.Events": "Events",

    "kb.upload.title": "Upload files",
    "kb.upload.hint": "Supports .md .txt .docx .pdf .html. You can put title / category / source_url / publisher / effective_date at the top of a file (one per line, ended by a blank line).",
    "kb.url.ph": "Source link (source_url), optional", "kb.pub.ph": "Publisher, e.g. HKUST ITSO", "kb.date.ph": "Effective date (if stated), optional",
    "kb.fromUrl.title": "Import from a link",
    "kb.fromUrl.hint": "Fetches the page text and strips navigation. WeChat, Tencent Docs and flip-books will say \"manual export needed\"; a link is never stored as if it were content.",
    "kb.fromUrl.btn": "Fetch and add",
    "kb.paste.title": "Paste text", "kb.paste.titlePh": "Title", "kb.paste.bodyPh": "Paste verified text...", "kb.paste.btn": "Add",
    "kb.links.title": "Link list (from Data.docx)",
    "kb.links.hint": "Fetched one by one; failures are marked as needing manual export. You can also paste any text containing links:",
    "kb.links.ph": "Paste text with links, then click \"Find links\"", "kb.links.parse": "Find links", "kb.links.fetchAll": "Fetch all",
    "kb.th.topic": "Topic", "kb.th.name": "Name", "kb.th.status": "Status", "kb.th.title": "Title", "kb.th.type": "Type",
    "kb.th.chunks": "Chunks", "kb.th.date": "Date",
    "kb.docs.title": "Documents in the knowledge base", "kb.stats": "· {d} docs / {c} chunks / {n} chars",
    "kb.pending": "Not fetched", "kb.fetching": "Fetching…", "kb.fetchBtn": "Fetch", "kb.delete": "Delete",
    "kb.confirmDelete": "Delete this document from the knowledge base?",
    "kb.dup": "Already exists, skipped", "kb.chunksAdded": "{n} chunks added", "kb.fetchOk": "Success: {chars} chars → {n} chunks",
    "kb.manual": "Manual export needed: ",

    "set.title": "Model settings", "set.preset": "Provider preset",
    "set.preset.hkust": "HKUST sponsored credits (AISC1000)", "set.preset.openai": "OpenAI", "set.preset.custom": "Custom (OpenAI-compatible)",
    "set.note.hkust": "HKUST sponsored credits are for AISC1000 course work only. Get your key by signing in at https://hkust.developer.azure-api.net/ and subscribing to \"HKUST GenAI (AISC1000 Dify)\". Do not share it.",
    "set.note.openai": "Requires a key created on the OpenAI API platform (not a ChatGPT login).",
    "set.note.custom": "Enter any OpenAI-compatible Base URL and model name.",
    "set.model": "Model name", "set.modelPh": "Use a model available to your account",
    "set.agent": "Agent mode (understands the question, picks the topic and plans the search first; needs an API key, off = plain retrieval)",
    "set.remember": "Remember the key only for this browser tab session (cleared when the tab closes)",
    "set.test": "Test connection", "set.clear": "Clear key", "set.testing": "Testing...", "set.cleared": "Cleared.",
    "set.ok": "Connected: {reply}",
    "set.privacy": "The key is only sent with each request to the local backend and forwarded to the API address you set; it is not stored in the database or logs. Your question and the retrieved passages are sent to that provider, so do not import sensitive material. Without a key only retrieval runs.",

    "log.title": "Q&A log (latest 200)", "log.export": "Export CSV",
    "log.th.time": "Time", "log.th.question": "Question", "log.th.mode": "Mode", "log.th.flags": "Flags", "log.th.ms": "Latency", "log.th.sources": "Sources",
  },
};

let LANG = (function () {
  const saved = localStorage.getItem("lang");
  if (saved === "zh" || saved === "en") return saved;
  return (navigator.language || "").toLowerCase().startsWith("zh") ? "zh" : "en";
})();

function t(key, vars) {
  let s = (I18N[LANG] && I18N[LANG][key]) ?? I18N.zh[key] ?? key;
  if (typeof s !== "string") return s;
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? vars[k] : m));
  return s;
}

/* Static HTML: data-i18n -> textContent, data-i18n-ph -> placeholder, data-i18n-title -> title */
function applyStaticI18n() {
  document.documentElement.lang = LANG;
  document.title = "HKUST Freshmen Assistant";
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
}
