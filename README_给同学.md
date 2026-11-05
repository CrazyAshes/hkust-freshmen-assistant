# HKUST 新生助手 / HKUST Freshmen Assistant

只读的校园问答机器人（宿舍、餐饮、打印、Wi-Fi、体育、校园指南），回答附官方来源。AISC1000 Group 19。
A read-only campus Q&A bot with cited sources. It cannot book, pay or submit anything.

## 启动 / Start

需要先装 Python 3.9 或以上：https://www.python.org/downloads/

**Mac**：解压后双击 `start.command`。如果提示"无法打开"，右键 → 打开；或在终端运行 `chmod +x start.command`。

**Windows / Linux**（在项目文件夹里打开终端）：

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # Linux: .venv/bin/pip
.venv\Scripts\python manage.py rebuild             # 第一次：建立搜索索引
.venv\Scripts\python server.py 8000
```

然后浏览器打开 http://127.0.0.1:8000

## 填 API Key

在页面的"设置"里填**你自己的** OpenAI API Key 和模型名。Key 只随你的提问发给模型接口，服务器不会把它写进数据库或日志；只有勾选"记住"时，才会保存在你自己浏览器的本地存储里（公用电脑请不要勾选）。
不填 Key 也能用，但只有检索，没有智能体规划和回答。**请不要把你的 Key 发给别人。**

## 试试这些问题

- Where can I print documents on campus, and how much does it cost?
- 先问 "Where can I print?"，再问 "How much does it cost?"
- 校园 Wi-Fi 怎么连？
- 一个知识库里没有的问题（比如签证费）：应该回答"无法确认"，而不是编造。

## 注意

- 这个包不含两本 MSSS 手册的原始 PDF（体积大），但它们整理后的文本已经在 `data/corpus/` 里。
- MSSS 的内容是学生社团写的经验，不是官方规则；营业时间、价格以官方页面为准。
- 本地运行默认只监听 127.0.0.1。若要对外提供 Demo，设置 `FRESHMEN_PUBLIC=1`（见 `.env.example`）：此时只开放聊天和只读接口，Key 只放在服务器环境变量里，并带限流。
- `.env` 里有真实 Key，**不要**打包、提交或发给别人；部署平台上请单独设置同名环境变量。
- 有问题或发现答错，请记下问题原文和回答，反馈给组里负责 Demo 的同学。

## 停止
在终端按 Ctrl+C。
