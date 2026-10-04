"""Hand-authored example of the reference layout; never claims an AI run."""
import json
from backend import storage as db
from backend.book_to_skill.builder import build_indexes,build_master,validate_package
from backend.book_to_skill.spec import REFERENCE
from backend.book_to_skill.retrieval import index_skills


def upgrade_demo(book_id):
    b=db.book(book_id)
    if not b or b['fileType']!='demo' or (b['metadata'] or {}).get('generatorVersion')!='demo-authored':return
    chapters=db.rows('SELECT * FROM chapters WHERE bookId=? ORDER BY idx',(book_id,))
    if len(chapters)!=3:return
    details=[
        ('知识需要上下文','当打算再次使用一个概念时，先用自己的话解释它，然后确认出处、条件与局限。',
         '1. 总结概念。\n2. 找到一个实际问题。\n3. 保存章节出处。\n4. 写出适用条件和局限。','只有页数，没有可以再次使用的知识。'),
        ('每周复盘','当尝试一个方法后，比较原先预期与实际结果，以改善下一次行动。',
         '1. 每天记录一个问题。\n2. 尝试一个小步骤。\n3. 观察结果。\n4. 每周比较预期与事实。','把复盘当成对自己的评分，忽略改善行动。'),
        ('区分事实、推理和建议','当一个观点很有说服力时，检查证据与隐含假设；跨书比较前确认讨论的问题相同。',
         '1. 区分事实、推理和建议。\n2. 检查证据。\n3. 检查适用条件。\n4. 比较观点前确认问题一致。','把有说服力的叙述直接当作普遍规律。')]
    files={f['path']:f['content'] for f in db.rows('SELECT path,content FROM skill_files WHERE bookId=?',(book_id,))}
    analyses=[];topics=[]
    for ch,(name,rule,how,avoid) in zip(chapters,details):
        files[f'chapters/ch{ch["idx"]+1:03d}.md']='# '+ch['title']+'\n\n## 核心思想\n\n'+rule+'\n\n## 何时使用\n\n'+rule+'\n\n## 操作步骤\n\n'+how+'\n\n## 反模式\n\n'+avoid+'\n\n## 演练示例\n\n示例文本没有提供完整演练。本文件不杜撰作者案例；可在问书中请求标明为推论的应用计划。\n\n## 来源\n\n'+ch['title']+'（人工编写的原创功能示例）'
        analyses.append({'concepts':[{'name':name,'chapter':ch['title']}]});topics.append([name])
    files['patterns.md']='# 阅读实践模式\n\n'+'\n\n'.join('## '+name+'\n\n**何时使用**：'+rule+'\n\n**如何操作**：\n'+how+'\n\n**失败方式**：'+avoid+'\n\n**来源**：第 '+str(i+1)+' 章。' for i,(name,rule,how,avoid) in enumerate(details))
    files['cheatsheet.md']='# 阅读决策速查表\n\n| 当你遇到 | 采取行动 | 理由与出处 |\n| --- | --- | --- |\n| 想复用一个知识点 | 核对出处、条件和局限 | 知识需要上下文（第一章） |\n| 预期与结果不同 | 每周复盘并改善下次行动 | 复盘的目标是改进行动（第二章） |\n| 比较两位作者 | 先确认是否讨论相同问题 | 避免把不同问题的答案直接对比（第三章） |\n\n原文未提供定量阈值或统计证据。'
    files['glossary.md']='# 术语表\n\n**上下文** — 一个观点的来源、适用条件和局限（第一章）。\n\n**复盘** — 比较预期与实际结果，改善下次行动（第二章）。\n\n**批判阅读** — 区分事实、推理和建议，检查证据与假设（第三章）。'
    cmap,tmap,crows,trows=build_indexes(chapters,analyses,topics)
    files['chapter-map.md']=cmap;files['topic-index.md']=tmap
    core={'core':'### 知识需要上下文\n\n当复用一个知识点时，先用自己的话说明，并记录来源、条件和局限（第一章）。\n\n### 每周复盘\n\n当尝试一个方法后，比较预期与事实；复盘用于改善下一次行动（第二章）。\n\n### 区分事实、推理和建议\n\n当比较观点时，检查证据与假设，并确认是否讨论同一问题（第三章）。',
        'voice':'以具体问题、适用条件和观察结果开展分析；不把有说服力的叙述等同于普遍规律。',
        'scope':'问书原创功能示例，人工编写，非真实出版物。三章短文没有完整案例、统计证据或定量阈值。'}
    distilled={p:v for p,v in files.items() if not p.startswith('references/') and p!='metadata.json'}
    files['SKILL.md']=build_master(b,'reading-compound',core,crows,trows,distilled)
    quality=validate_package({p:v for p,v in files.items() if not p.startswith('references/') and p!='metadata.json'})
    meta={**b['metadata'],'skillVersion':'2.0','generatorVersion':'demo-authored-2','generatorReference':{**REFERENCE,'integration':'authored-demo-of-spec'},
        'depth':'study','purpose':'all','chapterCount':3,'quality':quality,'exportPolicy':'distilled-by-default'}
    files['metadata.json']=json.dumps(meta,ensure_ascii=False,indent=2)
    with db.connect() as c:
        for path,content in files.items():
            c.execute('INSERT INTO skill_files VALUES(?,?,?,?) ON CONFLICT(bookId,path) DO UPDATE SET content=excluded.content',(db.uid(),book_id,path,content))
        c.execute('UPDATE skills SET metadata=? WHERE bookId=?',(json.dumps(meta,ensure_ascii=False),book_id))
    index_skills(book_id)
