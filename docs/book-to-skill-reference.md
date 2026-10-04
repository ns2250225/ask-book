# Book-to-Skill 参考与适配

上游：[virgiliojr94/book-to-skill](https://github.com/virgiliojr94/book-to-skill)。本次对照固定在提交 [`c108d25b0cb58e1bdc361f3de02ed9f37075152f`](https://github.com/virgiliojr94/book-to-skill/tree/c108d25b0cb58e1bdc361f3de02ed9f37075152f)，重点参考 [SKILL.md](https://github.com/virgiliojr94/book-to-skill/blob/c108d25b0cb58e1bdc361f3de02ed9f37075152f/SKILL.md) 的生成规范及 `docs/architecture.md`。

上游由确定性 Python 提取器与 Agent 执行的生成规范组成，**没有一个直接传入 API Key 就能生成 Skill 的 Python SDK**。问书以 Web Worker 适配其规范，保留已有 EPUB / PDF / TXT / Markdown 解析器、统一 OpenAI-compatible Gateway、SQLite 和浏览器密钥机制。没有安装上游到个人 Agent 的技能目录，没有自动创建仓库、发布书籍或调用 Claude 专用接口。

## 对照关系

| 上游原则 / 阶段 | 问书实现 |
| --- | --- |
| 提取结构，不是泛泛摘要 | `spec.py` 明确提取精确框架名、适用条件、操作步骤、原因、取舍、失败方式、决策规则、反模式、作者判断方式 |
| 内容类型 × 学习目的 | 类型由分类器判断；上传页选择综合、应用、心智模型或精简参考，前三种为 study，查阅为 reference |
| 自适应章节预算 | 文本类 reference / study 上限目标 1200 / 1800 Tokens；技术、科学、教材类为 1800 / 3000 Tokens；薄章节不填充 |
| 逐章按需加载 | `chapters/ch001.md` 等为蒸馏知识，保留框架、例子与条件；不是复制的原文章节 |
| 支持文件 | 固定 `glossary.md`、`patterns.md`、`cheatsheet.md`，同时保留 PRD 的自适应类型文件 |
| 决策辅助层 | cheatsheet 优先条件→行动→理由、决策树、取舍矩阵、作者明确给出的阈值与问题征兆；没有数值就明确说明 |
| 核心知识前置 | SKILL.md 首先展示书籍独有的核心知识，然后给用法、章节索引、主题索引、支持文件、判断方式与边界 |
| 主文件保持小 | 用估算器校验 SKILL.md ≤ 4000 Tokens；长书只放部分索引入口，完整索引在 chapter-map.md 与 topic-index.md |
| 主题索引导航 | 文件链接真实可用；问书 Router 先匹配主题索引和章节编号，实践问题先读取 cheatsheet 与 patterns；Inspector 中点击链接直接打开文件 |
| 不在可移植 Skill 中复制原书 | 默认 ZIP 导出不含 references/ 或 book.json 原书内容；用户勾选“包含原文”才导出完整证据档案 |
| 技能元数据与兼容 | 主文件只使用通用 name / description 前置字段；metadata.json 保存来源仓库、提交、规范适配方式、用途、深度与预算校验结果 |
| 可验证的输出 | 校验非空文件、代码块完整性、安全路径、内部链接与主文件预算；无效生成文件的检查点会清除以便重试 |

长书仍使用 Section → Chapter → Book 的 Map / Reduce。Reduce 不再把所有实体截到 15 项：已提取的实体通过确定性合并保留；单次模型输入使用有效 JSON 的有界视图，逐章知识与完整索引可继续访问各章内容。词法 / 混合搜索仍按需运行，而非每次装入整套 Skill。

## 兼容与迁移

- 新生成器版本：`wenshu-book-to-skill-2.0`，Skill 格式版本：`2.0`。
- 检查点带生成器版本命名空间；旧版分析不会冒充新版结果。旧版 Skill 不自动产生 AI 用量，需要从 Inspector 重新生成。
- 同版、同用途且文本不变时继续生成复用检查点。改变用途仍可复用相同结构化 Map / Reduce，章节深度和知识文件重新生成。
- 可直接导入上游常见 `SKILL.md + chapters/ + patterns/glossary/cheatsheet` 包；从主文件解析 name、标题和 Author。
- 只有蒸馏知识、没有原文的导入包仍可问书与检索 Skill，但不会将蒸馏知识伪装成原文，也不会产生伪原文出处；重新生成和原文追溯需包含原书。
- 原创示例已人工更新为此目录结构，元数据明确写“人工编写 · 示例”，不是实际模型转换结果。

## 与 CLI 规范的区别

Web 产品没有把上游的用户目录安装、symlink、GitHub 发布、Claude 专用工具、任意目录 / glob 多源输入及折入工作流搬到服务器执行。主文件预算采用中英文字符估算，不声称对所有模型都使用准确 Tokenizer。技术 PDF 暂沿用 PyMuPDF，不声称具有 Docling 对复杂表格、公式的解析能力。生成校验是结构、预算和链接校验，不是对模型真实性或提示注入的形式化证明；原文证据始终独立保留并明确区分。

上游 MIT 授权声明在 [third_party/book-to-skill-LICENSE.md](../third_party/book-to-skill-LICENSE.md)。该许可覆盖上游转换器及规范，不自动授予源书的分发权。
