# 问书 BookSkill — 产品需求文档 PRD

> 版本：V1.0 MVP  
> 产品类型：AI 阅读 / Book-to-Skill / 知识问答 Web 应用  
> 核心理念：把一本电子书转换成 AI 可以使用的 Skill，再让 AI 基于 Skill 与用户讨论整本书。

---

# 1. 产品概述

## 1.1 产品名称

暂定：

**BookSkill / 问书**

Slogan：

> 上传一本书，把它变成一个可以对话的 AI Skill。

---

## 1.2 产品定位

问书是一个基于 **Book-to-Skill** 的 AI 阅读网站。

用户上传一本电子书后，系统不是简单地把书切成 Chunk 建立向量数据库，而是通过 `book-to-skill` 将整本书进行：

- 内容解析
- 章节识别
- 知识提取
- 概念整理
- 方法论总结
- 人物 / 事件 / 观点关系整理
- Skill 指令生成
- Skill 知识文件生成

最终把一本书转换成一个可供 AI Agent 使用的：

```text
Book Skill
```

用户随后可以直接与这个 Skill 对话，例如：

```text
《原则》最核心的思想是什么？

作者为什么强调极度透明？

如果按照这本书的方法，我应该怎样管理一个 10 人创业团队？

把第三章的方法转化成一个每天可以执行的 checklist。

作者在第五章和第八章的观点有没有冲突？

如果让作者评价我的这个创业想法，他可能会怎么评价？
```

AI 不仅需要搜索原文，还应该调用从整本书蒸馏出的 Skill 来进行回答。

---

# 2. 产品目标

核心目标：

> 将“阅读一本书”转化成“获得一个可以长期对话和调用的知识 Skill”。

传统 AI 阅读工具通常采用：

```text
电子书
 ↓
文本解析
 ↓
Chunk
 ↓
Embedding
 ↓
Vector DB
 ↓
RAG
 ↓
回答
```

BookSkill 采用：

```text
电子书
 ↓
Book Parser
 ↓
章节结构
 ↓
Book-to-Skill
 ↓
知识蒸馏
 ↓
Book Skill
 ↓
Skill Agent
 ↓
用户提问
```

必要时再使用原文检索作为证据补充：

```text
Book Skill
    +
原文 Retrieval
    ↓
LLM
    ↓
回答 + 原文出处
```

因此系统采用：

**Skill First + Retrieval Second**

架构。

---

# 3. MVP 核心功能

MVP 只实现以下核心闭环：

```text
上传电子书
   ↓
解析电子书
   ↓
Book-to-Skill
   ↓
生成 Book Skill
   ↓
进入问书页面
   ↓
输入问题
   ↓
AI 调用 Skill
   ↓
必要时检索原文
   ↓
生成回答
```

MVP 暂时不加入：

- 社区
- 书籍商城
- 用户关注
- Skill 市场
- 多人协作
- 付费系统
- AI 自动购书
- DRM 破解

优先把：

**一本书 → Skill → 高质量问答**

做到最好。

---

# 4. 用户使用流程

## 4.1 第一次进入

首页显示：

```text
                问书 BookSkill

        把一本书变成一个 AI Skill

    [ 上传电子书 ]

支持 EPUB / PDF / TXT / Markdown

────────────────────────────

或者

[ 我的书架 ]
```

---

# 5. AI 模型配置

用户使用自己的 AI API。

系统本身不绑定特定 AI 厂商。

设置页面：

```text
AI 模型

API URL
┌──────────────────────────────┐
│ https://api.openai.com/v1    │
└──────────────────────────────┘

API Key
┌──────────────────────────────┐
│ sk-************************   │
└──────────────────────────────┘

Model
┌──────────────────────────────┐
│ gpt-5.6                      │
└──────────────────────────────┘

Temperature
[ 0.3 ]

Max Tokens
[ 8192 ]

[ 测试连接 ]

✓ API 可用
```

---

# 6. API 兼容设计

优先支持：

```text
OpenAI Compatible API
```

标准接口：

```http
POST {baseURL}/chat/completions
```

或者：

```http
POST {baseURL}/responses
```

推荐 MVP 优先实现 `chat/completions` 兼容层。

这样天然支持大量模型服务。

例如用户可以自行填写：

```text
OpenAI
OpenRouter
DeepSeek
SiliconFlow
Groq
Ollama
vLLM
LM Studio
自建 OpenAI Compatible API
```

系统只需要保存：

```json
{
  "baseURL": "",
  "apiKey": "",
  "model": "",
  "temperature": 0.3,
  "maxTokens": 8192
}
```

---

# 7. API Key 安全设计

API Key 属于敏感数据。

推荐 MVP：

浏览器端保存：

```text
IndexedDB
```

不要：

```text
上传到服务器数据库
```

请求流程优先：

```text
Browser
   ↓
LLM Provider
```

如果 Book-to-Skill 必须由服务器执行，则使用：

```text
Browser
 ↓
临时传递 Key
 ↓
Book Worker
 ↓
LLM API
```

Worker 使用结束立即销毁 Key。

服务器：

```text
禁止写日志
禁止写数据库
禁止持久化 API Key
```

界面明确显示：

> API Key 仅用于调用你配置的 AI 服务。

---

# 8. 上传电子书

点击：

```text
+ 上传一本书
```

支持：

| 格式 | MVP |
|---|---|
| EPUB | ✓ |
| PDF | ✓ |
| TXT | ✓ |
| Markdown | ✓ |
| MOBI | 后续 |
| AZW3 | 后续 |
| DOCX | 后续 |

推荐优先支持 EPUB。

原因是 EPUB 天然具有：

```text
书名
作者
目录
章节
正文
```

结构。

---

# 9. 上传页面

```text
┌──────────────────────────────────┐

          把一本书变成 Skill

        📖

     拖入 EPUB / PDF / TXT

          或

       [ 选择文件 ]

────────────────────────────────────

文件不会公开分享。

└──────────────────────────────────┘
```

上传成功：

```text
正在读取《原则》...

✓ 读取电子书
✓ 提取目录
✓ 识别章节
○ 分析知识结构
○ 生成 Book Skill
○ 构建原文索引
```

---

# 10. 电子书解析

解析结果统一转换成：

```json
{
  "title": "原则",
  "author": "Ray Dalio",
  "language": "zh",
  "chapters": [
    {
      "id": "chapter-1",
      "title": "我的历程",
      "content": "..."
    }
  ]
}
```

---

# 11. PDF 特殊处理

PDF 可能存在：

```text
双栏
页眉
页脚
页码
脚注
目录
扫描页
乱码
```

因此增加：

```text
PDF Normalizer
```

流程：

```text
PDF
 ↓
Text Extraction
 ↓
Layout Detection
 ↓
Header/Footer Removal
 ↓
Paragraph Merge
 ↓
Chapter Detection
 ↓
Book Structure
```

扫描 PDF 在 MVP 中可以提示：

> 当前 PDF 未检测到足够的可复制文本，暂不支持纯扫描版 PDF。

OCR 可作为后续版本功能。

---

# 12. Book-to-Skill 核心模块

这是整个产品最重要的部分。

输入：

```text
Book
```

输出：

```text
Skill Package
```

建议 Skill 使用目录形式：

```text
skills/
└── principles/
    ├── SKILL.md
    ├── metadata.json
    ├── overview.md
    ├── concepts.md
    ├── arguments.md
    ├── methods.md
    ├── examples.md
    ├── people.md
    ├── timeline.md
    ├── glossary.md
    ├── chapter-map.md
    └── references/
        ├── chapter-01.md
        ├── chapter-02.md
        └── ...
```

不同类型书籍可以动态决定实际生成哪些文件。

---

# 13. SKILL.md

例如：

```markdown
---
name: principles
description: Knowledge Skill generated from the book "Principles"
author: Ray Dalio
type: book
---

# Principles Book Skill

This skill contains structured knowledge extracted from
Ray Dalio's "Principles".

## Use this skill when

The user asks about:

- principles
- decision making
- radical transparency
- management
- organizations
- personal growth

## Answering rules

1. Prefer knowledge explicitly supported by the book.
2. Distinguish the author's ideas from your own inference.
3. Retrieve original passages when exact evidence is needed.
4. Never invent quotations.
5. Mention relevant chapters when possible.
```

---

# 14. 知识蒸馏流程

不能一次把整本几十万字的书直接发送给模型。

采用 Map → Reduce → Synthesis。

第一阶段：

```text
Chapter 1 → Chapter Skill
Chapter 2 → Chapter Skill
Chapter 3 → Chapter Skill
...
```

每章提取：

```text
summary
concepts
claims
arguments
methods
people
events
examples
quotes references
questions
connections
```

第二阶段：

```text
Chapter Skills
       ↓
Cross-Chapter Analysis
```

分析：

```text
重复观点
核心思想
概念关系
观点演变
因果关系
冲突观点
重要案例
方法论
```

第三阶段：

```text
Book Synthesis
```

最终生成：

```text
SKILL.md
overview.md
concepts.md
arguments.md
methods.md
...
```

---

# 15. 自适应 Skill

不同类型的书不能强制使用完全相同的 Skill Schema。

系统首先判断书籍类型：

```text
小说
商业
历史
哲学
技术
科学
传记
心理学
教材
工具书
其他
```

然后选择不同知识结构。

例如小说：

```text
characters.md
relationships.md
timeline.md
locations.md
themes.md
plot.md
```

商业书：

```text
concepts.md
frameworks.md
methods.md
cases.md
principles.md
```

技术书：

```text
concepts.md
architecture.md
patterns.md
examples.md
apis.md
pitfalls.md
```

历史书：

```text
people.md
events.md
timeline.md
locations.md
causality.md
```

---

# 16. Skill 生成进度

Book-to-Skill 可能需要较长时间。

必须提供可视化进度。

例如：

```text
《原则》

正在把这本书变成 Skill...

████████████████░░░░  72%

✓ 读取 593 页
✓ 识别 31 个章节
✓ 分析章节知识
✓ 提取 126 个核心概念
→ 正在建立概念关系
○ 生成 SKILL.md
○ 构建原文索引

预计还需要约 2 分钟
```

下面可以动态显示：

```text
刚刚发现：

「极度透明」
        ↓
「可信度加权决策」
        ↓
「创意择优」
```

让等待过程本身具有阅读感。

---

# 17. 我的书架

首页主要页面：

```text
我的书架

[ + 添加书籍 ]

┌──────────┐
│  BOOK    │
│  COVER   │
└──────────┘
原则
Ray Dalio

Skill ✓

┌──────────┐
│  BOOK    │
│  COVER   │
└──────────┘
人类简史
Yuval Noah Harari

Skill ✓
```

状态：

```text
未处理
解析中
Skill 生成中
可问书
失败
```

---

# 18. 问书页面

点击一本书进入：

```text
┌──────────────────────────────────────────────────────┐
│ ← 书架      《原则》              ⚙ Skill     ⋮      │
├──────────────┬───────────────────────────────────────┤
│              │                                       │
│ 📖 原则      │       你想问这本书什么？              │
│ Ray Dalio    │                                       │
│              │     [ 这本书最重要的思想是什么？ ]    │
│ 目录         │                                       │
│              │     [ 帮我总结作者的方法论 ]          │
│ 第一章       │                                       │
│ 第二章       │     [ 这本书适合创业者吗？ ]          │
│ 第三章       │                                       │
│ ...          │                                       │
│              │                                       │
│ Skill        │                                       │
│ ● 已加载     │                                       │
├──────────────┴───────────────────────────────────────┤
│ 问这本书任何问题...                         [ ↑ ]   │
└──────────────────────────────────────────────────────┘
```

---

# 19. AI Agent 工作流程

用户：

```text
作者为什么认为犯错是一件好事？
```

系统首先让 Agent 判断：

```text
Question
 ↓
Intent Analysis
 ↓
Skill Router
```

确定需要：

```text
concepts.md
methods.md
chapter-map.md
```

Agent 获取 Skill 后判断：

```text
是否需要原文证据？
```

如果需要：

```text
Retrieval
 ↓
找到相关章节
 ↓
返回相关 Passage
```

最终：

```text
Question

   ↓

Book Skill
   +
Relevant Original Text
   +
Conversation Context

   ↓

LLM

   ↓

Answer
```

---

# 20. 回答形式

回答不要只是普通 ChatGPT 文本。

例如：

```text
作者认为犯错本身并不是坏事，真正危险的是
“无法从错误中建立反馈循环”。

他把这个过程概括为：

痛苦
 ↓
反思
 ↓
找到原因
 ↓
建立原则
 ↓
改进决策

因此，在 Dalio 的框架中，错误实际上是一种
获得现实反馈的机制。

📖 相关内容

第三章 · 拥抱现实，应对现实
第五章 · 运用五步流程实现人生愿望

[查看原文]
```

---

# 21. 原文引用

AI 回答中的观点尽可能绑定来源。

例如：

```text
作者认为组织中的透明度能够降低隐藏问题的成本。[1]

同时，他认为透明本身并不足够，还需要建立
可信度加权的决策机制。[2]
```

下面：

```text
来源

[1] 第 7 章 · 极度透明
[2] 第 9 章 · 可信度加权决策
```

点击来源：

右侧弹出：

```text
原文

第 7 章

────────────────

……

────────────────

[打开完整章节]
```

避免模型生成不存在的原文引用。

---

# 22. Skill Inspector

用户可以点击：

```text
查看 Skill
```

进入 Skill Inspector。

```text
《原则》Skill

Overview

Core Concepts      126
Arguments           84
Methods             32
People              17
Examples            63
Chapters            31
```

---

# 23. Skill 文件浏览器

高级用户可以直接查看生成结果：

```text
📦 principles

├── SKILL.md
├── overview.md
├── concepts.md
├── arguments.md
├── methods.md
├── examples.md
├── glossary.md
├── chapter-map.md
└── references
```

点击：

```text
concepts.md
```

显示：

```markdown
# Core Concepts

## Radical Transparency

Definition:
...

Related concepts:

- Believability-weighted decision making
- Idea meritocracy

Appears in:

Chapter 7
Chapter 8
Chapter 9
```

---

# 24. Skill 搜索

提供：

```text
搜索 Skill...
```

例如：

```text
透明
```

结果：

```text
Concept
极度透明

Method
可信度加权决策

Argument
为什么透明可以提高组织效率
```

---

# 25. 推荐问题

Skill 创建完成后自动生成：

```text
推荐问题
```

分为：

```text
快速了解

这本书讲了什么？
最重要的 10 个观点是什么？
作者最核心的思想是什么？

深入理解

作者有哪些反直觉观点？
哪些章节之间存在联系？
作者的论证有什么漏洞？

实际应用

如何把这本书用于工作？
帮我制定一个实践计划。
把这本书转化成 Checklist。

批判阅读

哪些观点缺乏证据？
作者有哪些隐含假设？
有哪些观点可能已经过时？
```

---

# 26. 对话记忆

每本书拥有独立 Session。

结构：

```text
Book
 ├── Skill
 └── Conversations
      ├── Session 1
      ├── Session 2
      └── Session 3
```

用户可以：

```text
新建对话
查看历史对话
删除对话
重命名对话
```

---

# 27. 上下文策略

不能每次把整个 Skill 全部放入 Prompt。

使用：

```text
Skill Router
```

流程：

```text
Question

 ↓

SKILL.md

 ↓

判断需要哪些 Skill 文件

 ↓

Skill Search

 ↓

加载相关内容

 ↓

必要时 Retrieval

 ↓

LLM
```

例如：

```text
《三体》里叶文洁为什么这样做？
```

Router：

```text
characters.md
timeline.md
plot.md
```

而不是加载：

```text
整本 Skill
```

---

# 28. Skill Retrieval

Skill 文件本身也建立索引。

建议：

```text
BM25
+
Embedding
```

混合搜索：

```text
Hybrid Search
```

评分：

```text
score =
0.4 × BM25
+
0.6 × Vector Similarity
```

Embedding 可以允许用户单独配置。

但为了 MVP 简单，可以首先使用：

```text
BM25 / FTS
```

这样即使用户的 AI API 没有 Embedding API，也可以正常工作。

---

# 29. 原文索引

每个 Passage 保存：

```json
{
  "bookId": "...",
  "chapterId": "...",
  "chapter": "第三章",
  "paragraph": 18,
  "text": "...",
  "start": 12340,
  "end": 12890
}
```

这样回答可以精确关联：

```text
书
→ 章节
→ 段落
→ 原文
```

---

# 30. Prompt 架构

System Prompt：

```text
You are a BookSkill reading agent.

Your task is to answer questions using the knowledge
contained in the provided Book Skill.

Rules:

1. Treat the Book Skill as the primary knowledge source.
2. Distinguish book content from your own reasoning.
3. Never fabricate quotes.
4. If exact evidence is required, retrieve the original text.
5. Cite chapters whenever possible.
6. If the book does not contain the answer, explicitly say so.
7. You may analyze, compare and infer, but label inference clearly.
```

---

# 31. 防止 AI 幻觉

回答划分为三种知识：

```text
BOOK_FACT
INFERENCE
GENERAL_KNOWLEDGE
```

例如：

```text
根据本书：
作者认为……

我的分析：
这个观点意味着……

补充背景：
现代组织理论中……
```

这样避免：

```text
AI 自己的观点
```

被用户误认为：

```text
作者观点
```

---

# 32. Skill 更新

Book Skill 应保存：

```text
skillVersion
generatorVersion
model
generatedAt
bookHash
```

例如：

```json
{
  "skillVersion": "1.0",
  "generatorVersion": "book-to-skill-0.3",
  "model": "gpt-5.6",
  "bookHash": "sha256:...",
  "generatedAt": "..."
}
```

未来 Book-to-Skill 算法升级后：

```text
发现新的 Skill 生成器

[重新生成 Skill]
```

---

# 33. Skill 导出

这是非常重要的功能。

允许：

```text
导出 Skill
```

生成：

```text
principles.skill.zip
```

内部：

```text
principles/
├── SKILL.md
├── metadata.json
├── overview.md
├── concepts.md
├── methods.md
├── arguments.md
└── references/
```

用户可以把 Skill 用于：

```text
Claude Code
Codex
OpenClaw
Agent
自建 AI
其他支持 Skills 的系统
```

从而让 BookSkill 不只是“问书网站”，还是：

> **书籍 → AI Skill 转换器。**

---

# 34. Skill 导入

同时支持：

```text
导入 Skill
```

用户可以直接上传：

```text
.skill.zip
```

无需重新处理原始书籍。

---

# 35. 数据模型

## Book

```text
id
title
author
cover
language
fileType
fileHash
status
createdAt
```

## Chapter

```text
id
bookId
index
title
content
```

## Skill

```text
id
bookId
name
version
generatorVersion
model
status
createdAt
```

## SkillFile

```text
id
skillId
path
content
type
```

## Passage

```text
id
bookId
chapterId
text
position
searchIndex
```

## Conversation

```text
id
bookId
title
createdAt
updatedAt
```

## Message

```text
id
conversationId
role
content
references
createdAt
```

---

# 36. 推荐技术架构

前端：

```text
Vue 3
TypeScript
Vite
Pinia
Tailwind CSS
```

后端：

```text
FastAPI
Python
```

数据库：

```text
SQLite
```

电子书：

```text
EPUB → ebooklib
PDF → PyMuPDF
TXT → Python
Markdown → markdown parser
```

全文搜索：

```text
SQLite FTS5
```

后台任务：

MVP：

```text
FastAPI BackgroundTasks
```

正式版：

```text
Redis
+
Celery / RQ
```

---

# 37. 系统架构

```text
                    Browser
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
      Library       Book Chat      Settings
        │              │              │
        └──────────────┼──────────────┘
                       │
                       ▼
                  FastAPI API
                       │
         ┌─────────────┼─────────────┐
         │             │             │
         ▼             ▼             ▼
   Book Parser    Skill Agent    Book Storage
         │             │
         ▼             │
   Book-to-Skill       │
         │             │
         ▼             │
    Skill Store ───────┤
         │             │
         ▼             ▼
      FTS5         LLM Gateway
                       │
                       ▼
                User AI Provider
```

---

# 38. Book-to-Skill Worker

这是后端独立核心模块：

```text
book_to_skill/
├── parser/
├── classifier/
├── chapter_analyzer/
├── concept_extractor/
├── synthesizer/
├── skill_builder/
├── retrieval/
└── exporter/
```

核心接口：

```python
generate_skill(
    book,
    llm_config
) -> Skill
```

---

# 39. LLM Gateway

所有 AI 请求统一经过：

```text
LLMGateway
```

接口：

```python
chat(
    messages,
    model,
    base_url,
    api_key
)
```

Book-to-Skill 与问书 Agent 都只调用：

```text
LLMGateway
```

不要直接依赖 OpenAI SDK 的特定模型逻辑。

这样未来可以轻松支持：

```text
OpenAI
OpenRouter
DeepSeek
Ollama
vLLM
LM Studio
其他兼容服务
```

---

# 40. 文件存储

建议：

```text
data/

books/
  {book_id}/
      original.epub
      parsed.json

skills/
  {book_id}/
      SKILL.md
      overview.md
      concepts.md
      ...

conversations/
```

SQLite：

```text
data/bookskill.db
```

---

# 41. 删除书籍

点击：

```text
删除书籍
```

弹窗：

```text
删除《原则》？

将同时删除：

• 原始电子书
• Book Skill
• 原文索引
• 所有问书记录

此操作无法恢复。

[取消] [删除]
```

---

# 42. UI 风格

整体采用：

**现代极简数字阅读器 + AI IDE**

避免传统 ChatGPT 克隆风格。

主色：

```text
Paper White
Ink Black
Warm Gray
```

视觉元素：

```text
纸张
书页
书签
目录
引用
高亮
知识节点
```

字体：

中文：

```text
Noto Sans SC
Noto Serif SC
```

英文：

```text
Inter
Source Serif
```

正文回答可以使用 Serif，形成阅读感。

---

# 43. 首页

首页不要直接显示聊天框。

而应该强调：

```text
你的 AI 书架
```

布局：

```text
问书

把书变成可以对话的知识 Skill

[ + 添加一本书 ]

────────────────────────

最近阅读

原则
人类简史
思考，快与慢
Designing Data-Intensive Applications
```

---

# 44. 空状态设计

没有书：

```text
📚

你的 AI 书架还是空的

上传一本电子书，
把它变成一个可以与你对话的 Skill。

[ 上传第一本书 ]
```

---

# 45. 错误处理

## API Key 无效

```text
无法连接 AI

401 Unauthorized

请检查：

• API URL
• API Key
• Model

[打开 AI 设置]
```

## Context 超限

自动：

```text
缩短 Skill Context
→ 再次检索
→ 重试
```

## Book-to-Skill 中断

保存：

```text
checkpoint
```

允许：

```text
继续生成
```

而不是从头开始。

---

# 46. 成本控制

一本书可能几十万字，如果粗暴调用模型成本会非常高。

Book-to-Skill 必须支持：

```text
Incremental Processing
```

保存每章分析结果：

```text
chapter_001.skill.json
chapter_002.skill.json
chapter_003.skill.json
```

已经分析过的章节：

```text
不重复调用 LLM
```

根据：

```text
chapterHash
```

判断内容是否发生变化。

---

# 47. Token 预算

生成 Skill 前估算：

```text
这本书约 186,000 Tokens

预计：

章节分析：32 次
全书综合：4 次

预计 AI 请求：36 次

[开始转换]
```

如果 API 能获得价格信息，可以后续增加：

```text
预计费用
```

但 MVP 不强制实现。

---

# 48. 长书处理

例如一本：

```text
1,000 页
500,000 Tokens
```

采用：

```text
Book
 ↓
Chapter
 ↓
Section
 ↓
Section Skill
 ↓
Chapter Skill
 ↓
Book Skill
```

形成树形压缩：

```text
Book Skill
├── Chapter Skill
│   ├── Section Skill
│   └── Section Skill
├── Chapter Skill
└── Chapter Skill
```

这样理论上可以处理非常长的书。

---

# 49. 问书 Agent 工具

Agent 提供以下内部 Tools：

```text
search_skill(query)

read_skill_file(path)

search_book(query)

read_chapter(chapter_id)

read_passage(passage_id)

get_book_structure()

get_conversation_context()
```

Agent 自己决定调用哪个工具。

例如：

```text
用户：
作者对失败怎么看？

Agent：

search_skill("失败")
 ↓
read_skill_file("concepts.md")
 ↓
search_book("失败 错误 痛苦")
 ↓
read_passage(...)
 ↓
Answer
```

---

# 50. 普通 RAG 与 BookSkill 的区别

普通 RAG：

```text
问题
 ↓
搜索相似文本
 ↓
LLM
```

BookSkill：

```text
问题
 ↓
理解问题
 ↓
调用整本书蒸馏出的知识结构
 ↓
找到相关概念 / 方法 / 论点
 ↓
必要时回到原文
 ↓
综合推理
 ↓
回答
```

核心区别：

> **RAG 找“句子”，Skill 找“知识”。**

---

# 51. MVP 页面

只需要 5 个核心页面：

```text
/
书架

/books/new
上传书籍

/books/:id
问书

/books/:id/skill
Skill Inspector

/settings
AI 设置
```

---

# 52. MVP 优先级

## P0

必须完成：

```text
上传 EPUB
上传 PDF
上传 TXT

书籍解析

Book-to-Skill

SKILL.md

Skill Files

Skill Inspector

问书

Skill Search

原文 Search

章节引用

自定义：

API URL
API Key
Model

SQLite

Skill 导出
```

## P1

后续：

```text
Skill 导入
Markdown
多 Session
推荐问题
生成进度
断点续传
Hybrid Search
```

## P2

未来：

```text
Skill Marketplace
多书联合问答
知识图谱
书籍对比
读书笔记
自动 Flashcards
自动 Quiz
学习模式
```

---

# 53. 后续核心功能：多书 Skill

未来允许：

```text
选择：

☑ 原则
☑ 思考，快与慢
☑ 穷查理宝典

[开始对话]
```

形成：

```text
Multi-Skill Agent
```

用户：

```text
这三本书对于“如何做正确决策”
分别有什么看法？
```

Agent：

```text
Principles Skill
       +
Thinking Fast and Slow Skill
       +
Poor Charlie's Almanack Skill
       ↓
Cross-Skill Reasoning
       ↓
Answer
```

这会成为产品非常重要的差异化能力。

---

# 54. 后续功能：Book Skill Graph

将 Skill 中：

```text
人物
概念
事件
方法
观点
章节
```

建立关系：

```text
        Radical Transparency
             │
             ▼
      Idea Meritocracy
        /           \
       ▼             ▼
Believability     Decision
Weighted          Making
```

用户可以：

```text
探索一本书
```

而不仅仅是聊天。

---

# 55. 后续功能：从书到行动

Skill 不只是回答问题。

还可以：

```text
把这本书转化成：

[行动计划]
[Checklist]
[学习计划]
[考试题]
[Flashcards]
[思维导图]
[课程]
```

例如：

```text
把《原则》转换成一个 30 天实践计划。
```

Agent 基于 Skill 自动生成。

---

# 56. 产品核心原则

整个产品开发过程中必须坚持：

### 原则一：Skill 是第一等公民

不要把产品做成：

```text
又一个 PDF Chat。
```

核心资产必须是：

```text
Book Skill
```

---

### 原则二：Skill 可查看

用户必须能够看到：

```text
AI 到底从书里学到了什么。
```

因此必须提供：

```text
Skill Inspector
```

---

### 原则三：Skill 可导出

生成的 Skill 属于用户。

允许：

```text
Export
```

让用户可以在其他 Agent 中使用。

---

### 原则四：回答可追溯

所有重要书籍观点：

```text
Skill
 ↓
Chapter
 ↓
Original Text
```

能够回到原文。

---

### 原则五：AI 与书籍观点分离

必须区分：

```text
作者说的

AI 推理的

外部知识
```

避免用户误认为 AI 的幻觉就是作者观点。

---

# 57. MVP 最终体验

用户第一次进入：

```text
上传《原则.epub》
```

系统：

```text
正在读取这本书...
```

随后：

```text
发现 31 个章节

正在将《原则》转换为 AI Skill...

████████████████████ 100%

✓ 126 个核心概念
✓ 32 个方法
✓ 84 个重要论点
✓ 63 个案例

Book Skill 创建完成

[开始问书]
```

用户：

```text
这本书最值得我真正实践的三个方法是什么？
```

系统调用：

```text
SKILL.md
 ↓
methods.md
 ↓
concepts.md
 ↓
chapter-map.md
 ↓
相关原文
```

最终给出：

```text
如果只选择三个，我会优先考虑：

1. 五步流程
2. 痛苦 + 反思 = 进步
3. 可信度加权决策

为什么是这三个？

……

📖 来自本书
第三章
第五章
第八章

[查看原文]
```

至此形成完整产品闭环：

**Book → Skill → Ask → Evidence → Understanding → Action**

---

# 58. 一句话产品定义

> **问书不是让 AI 搜索一本书，而是先让 AI 把一本书真正“学成一个 Skill”，然后让用户直接与这份知识能力对话。**