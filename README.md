# AI 贸易邮件 Agent (Email Agent)

一个基于大语言模型（LLM）的自动化邮件处理 Agent Demo。能够自动拉取邮箱未读邮件，进行意图分类、实体提取、非业务拦截，并生成专业的回复草稿，辅助外贸业务员提升工作效率。

## 核心功能

- **自动拉取**：通过 IMAP 协议连接邮箱，拉取所有未读邮件。
- **智能分析**：调用 LLM 对邮件进行分类（询盘、跟进、投诉、样品、物流、其他），提取客户名称、产品型号、数量、交期等核心实体，并生成一句话摘要。
- **业务拦截**：自动识别垃圾邮件或非业务邮件，直接跳过后续处理流程，节省算力。
- **系统模拟关联**：模拟关联 CRM / OMS 系统，输出客户匹配状态和产品库调取记录。
- **草稿生成**：根据邮件意图和提取的实体，自动撰写语气专业的回复草稿（不编造价格和交期，用占位符替代）。
- **结果落盘**：将生成的回复草稿按邮件序号和主题保存为 Markdown 文件（保存在 `drafts/` 目录），方便人工审核。

## 目录结构

```text
email-agent/
├── .env.example           # 环境变量示例（需复制为 .env 并填写真实值）
├── .gitignore             # Git 忽略规则（已排除 .env 和 .venv）
├── requirements.txt       # 项目依赖
├── config.py              # 读取 .env 配置
├── llm_client.py          # LLM 接口封装（邮件分析、草稿生成）
├── email_agent.py         # 核心业务逻辑（拉取、提取、拦截、生成）
├── main.py                # 项目入口
└── drafts/                # 运行后自动生成的草稿目录（已脱敏/清空）
```

## 环境准备

1. Python 3.10 或更高版本

2. 一个支持 IMAP 协议的邮箱账号（如 QQ 邮箱、163 邮箱、Gmail 等，需获取授权码）

3. 一个兼容 OpenAI 接口规范的大模型 API Key（如 OpenAI、DeepSeek、通义千问等）

## 流程
### 1.克隆项目并安装依赖

```bash
git clone <你的仓库地址>
cd email-agent
python -m venv .venv
source .venv/bin/activate  # Windows 系统使用 .venv\Scripts\activate
pip install -r requirements.txt
```

### 2.配置环境变量
复制 .env.example 文件并重命名为 .env，填入真实信息：

```bash
cp .env.example .env
```

编辑 .env 文件：

· 邮箱配置（注意：EMAIL_PASS 填写的是邮箱授权码，不是登录密码）
EMAIL_USER=your_email@example.com
EMAIL_PASS=your_authorization_code
IMAP_SERVER=imap.example.com

· LLM 配置（兼容 OpenAI 接口）
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

### 3.运行 Agent

```bash
python main.py
```

### 4.查看结果

终端输出：实时打印拉取进度、邮件分类结果、提取的实体信息以及生成的回复草稿。

文件输出：每封处理成功的邮件，会在 drafts/ 目录下生成对应的 Markdown 文件，命名格式为 序号_主题.md，包含分类、紧急度、摘要、实体和完整草稿。

### 注意事项
目前仅拉取未读邮件（UNSEEN），不支持增量同步或按时间范围拉取。

process_crm_oms 目前为模拟打印，未接入真实的 CRM/OMS 接口。

生成的回复草稿暂不支持自动发送，需人工审核后手动发送（出于业务安全考虑，这是有意为之）。

若邮件没有主题，系统会默认命名为“无主题”。

### 可能的扩展方向

1.将草稿通过API推送给企业微信/飞书通知业务员审核
2.完善可视化工作，支持邮箱、大模型的简便自主选择