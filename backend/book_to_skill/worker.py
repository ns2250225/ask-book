import asyncio, json, time, shutil
from backend import storage as db, llm
from backend.book_to_skill.parser import sections, content_hash, estimate_tokens
from backend.book_to_skill.retrieval import index_book,index_skills
from backend.book_to_skill.spec import (GENERATOR_VERSION,REFERENCE,PURPOSES,FIELDS,SYSTEM,
    depth_for,chapter_budget,fields_prompt,chapter_prompt,file_prompt,core_prompt)
from backend.book_to_skill.builder import (chapter_path,merge_analysis,bounded_context,
    build_indexes,build_master,validate_package)

TASKS={}
SCHEMAS={
 '小说':['characters','relationships','timeline','locations','themes','plot'],
 '商业':['concepts','frameworks','methods','cases','principles'],
 '技术':['concepts','architecture','patterns','examples','apis','pitfalls'],
 '历史':['people','events','timeline','locations','causality'],
 '哲学':['concepts','arguments','themes','connections'],
 '科学':['concepts','arguments','examples','methods'],
 '传记':['people','events','timeline','themes'],
 '心理学':['concepts','methods','examples','arguments'],
 '教材':['concepts','methods','examples','glossary'],
 '工具书':['concepts','methods','examples','glossary'],
 '其他':['concepts','arguments','methods','examples','people','timeline','glossary']}


def checkpoint(book_id,key):
    row=db.one('SELECT value FROM checkpoints WHERE bookId=? AND hash=?',(book_id,GENERATOR_VERSION+':'+key))
    return json.loads(row['value']) if row else None

def save_checkpoint(book_id,key,value):
    db.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?,?)',(book_id,GENERATOR_VERSION+':'+key,json.dumps(value,ensure_ascii=False)))

def discard(book_id,key):
    db.execute('DELETE FROM checkpoints WHERE bookId=? AND hash=?',(book_id,GENERATOR_VERSION+':'+key))

def reduction_calls(count):
    calls=0
    while count>1:
        calls+=count//6+(1 if count%6>1 else 0)
        count=(count+5)//6
    return calls

def knowledge_files(kind):
    return list(dict.fromkeys(['overview.md','arguments.md','glossary.md','patterns.md','cheatsheet.md']+[x+'.md' for x in SCHEMAS.get(kind,SCHEMAS['其他'])]))

def estimate(book_id,purpose='all'):
    ch=db.rows('SELECT * FROM chapters WHERE bookId=? ORDER BY idx',(book_id,))
    units=[sections(x['content']) for x in ch]; n=sum(map(len,units))
    tokens=sum(estimate_tokens(x['content']) for x in ch)
    b=db.book(book_id);kind=b['kind'] if b else '其他';depth=depth_for(purpose)
    reductions=sum(reduction_calls(len(x)) for x in units)+reduction_calls(len(ch))
    output=len(ch)*chapter_budget(kind,depth)+4000+sum({'glossary.md':1500,'patterns.md':2000,'cheatsheet.md':1200}.get(p,2000) for p in knowledge_files(kind))
    cached=db.one('SELECT count(*) n FROM checkpoints WHERE bookId=? AND hash LIKE ?',(book_id,GENERATOR_VERSION+':%'))['n']
    return {'tokens':tokens,'inputTokens':int(tokens*1.3),'outputTokens':output,'chapters':len(ch),'sections':n,
        'requests':n+reductions+len(ch)+len(knowledge_files(kind))+2,'checkpoints':cached,'estimated':True,
        'depth':depth,'purpose':purpose,'generatorVersion':GENERATOR_VERSION}

async def cached_call(book_id,key,config,prompt):
    value=checkpoint(book_id,key)
    if value is not None:return value
    # Knowledge length targets belong in the prompt. A hidden per-file API
    # cap also consumes reasoning tokens and makes raising Max Tokens useless.
    value=await llm.json_chat(config,prompt,SYSTEM)
    save_checkpoint(book_id,key,value)
    return value

async def content_call(book_id,config,prompt):
    key='file:'+content_hash(prompt)
    value=await cached_call(book_id,key,config,prompt)
    if not isinstance(value.get('content'),str) or not value['content'].strip():
        discard(book_id,key)
        raise ValueError('模型未返回有效的蒸馏知识文件，请继续生成或提高 Max Tokens')
    # A malformed file should be regenerable; don't poison its checkpoint.
    if value['content'].count('```')%2:
        discard(book_id,key)
        raise ValueError('模型返回了不完整的代码块，请继续生成或提高 Max Tokens')
    return value

async def compress(book_id,config,items,label):
    level=items
    while len(level)>1:
        result=[]
        for i in range(0,len(level),6):
            group=level[i:i+6]
            if len(group)==1:result.extend(group);continue
            merged=merge_analysis(group,{})
            payload=bounded_context(merged,36000)
            payload['childSummaries']=[str(x.get('summary',''))[:1500] for x in group]
            prompt=f'综合这些{label}，准确提炼核心框架、决策规则、反模式、作者取舍、跨章节关系和冲突。返回 summary 字符串及 '+','.join(FIELDS)+' 数组，保留真实章节出处。不要把技术方法泛化为概述。\n'+json.dumps(payload,ensure_ascii=False)
            value=await cached_call(book_id,'reduce:'+content_hash(prompt),config,prompt)
            result.append(merge_analysis(group,value))
        level=result
    return level[0] if level else {}

async def generate_skill(book_id,config,purpose='all'):
    started=time.time()
    try:
        if purpose not in PURPOSES:raise ValueError('无效的 Skill 用途')
        depth=depth_for(purpose)
        b=db.book(book_id); chapters=db.rows('SELECT * FROM chapters WHERE bookId=? ORDER BY idx',(book_id,))
        if not chapters:raise ValueError('没有可处理章节；导入的 Skill 可直接使用')
        db.update_book(book_id,status='generating',progress=8,stage='识别书籍类型与 Skill 深度',error='')
        sample='\n'.join(x['title']+'\n'+x['content'][:1500] for x in chapters[:8])
        classify_prompt='判断书籍类型，kind 必须为以下之一：'+','.join(SCHEMAS)+f'。返回 {{"kind":"..."}}。书名：{b["title"]}\n'+sample
        classification=await cached_call(book_id,'classify:'+content_hash(classify_prompt),config,classify_prompt)
        kind=classification.get('kind','其他');kind=kind if kind in SCHEMAS else '其他';db.update_book(book_id,kind=kind)
        total=sum(len(sections(x['content'])) for x in chapters);completed=0;analyses=[];files={};chapter_topics=[];file_keys=[]
        for ch in chapters:
            parts=[]
            for i,section in enumerate(sections(ch['content'])):
                db.update_book(book_id,progress=10+int(completed/max(total,1)*55),stage=f'提取框架与决策结构「{ch["title"]}」· {completed+1}/{total} 个片段')
                prompt=fields_prompt(b['title'],kind,ch,section,i)
                value=await cached_call(book_id,'map:'+content_hash(prompt),config,prompt)
                value['chapter']=ch['title'];parts.append(value);completed+=1
            analysis=await compress(book_id,config,parts,ch['title']);analysis['chapter']=ch['title'];analyses.append(analysis)
            db.update_book(book_id,stage=f'生成按需章节知识「{ch["title"]}」')
            prompt=chapter_prompt(b['title'],kind,ch,bounded_context(analysis,36000),depth)
            file_keys.append('file:'+content_hash(prompt))
            value=await content_call(book_id,config,prompt)
            files[chapter_path(ch)]=value['content']
            topics=value.get('topics',[]);chapter_topics.append([t for t in topics if isinstance(t,str)][:30] if isinstance(topics,list) else [])
            stats={field:sum(len(x.get(field,[])) if isinstance(x.get(field),list) else 0 for x in analyses) for field in ('concepts','methods','arguments','frameworks','anti_patterns','decision_rules')}
            stats.update({'chapters':len(chapters),'elapsed':int(time.time()-started)})
            db.update_book(book_id,stats=json.dumps(stats,ensure_ascii=False))
        db.update_book(book_id,progress=68,stage='综合全书框架、作者判断方式与跨章节联系')
        synthesis=await compress(book_id,config,analyses,'章节知识')
        prompt=core_prompt(b['title'],b['author'],kind,bounded_context(synthesis,36000,['frameworks','mental_models','decision_rules','principles','voice','limitations']),purpose)
        core_key='core:'+content_hash(prompt)
        core=await cached_call(book_id,core_key,config,prompt)
        if not isinstance(core.get('core'),str) or not core['core'].strip():
            discard(book_id,core_key);raise ValueError('模型未生成核心框架，请继续生成')
        core={k:v for k,v in core.items() if k=='questions' or isinstance(v,str)}
        filenames=knowledge_files(kind)
        for i,path in enumerate(filenames):
            db.update_book(book_id,progress=73+int(i/max(len(filenames),1)*18),stage='生成知识工具 · '+path)
            priorities={'patterns.md':['methods','frameworks','code_examples','tradeoffs','anti_patterns'],
                'cheatsheet.md':['decision_rules','thresholds','heuristics','tradeoffs','principles'],
                'glossary.md':['concepts','frameworks','people','events']}.get(path,[])
            prompt=file_prompt(path,b['title'],kind,bounded_context(synthesis,36000,priorities),purpose)
            file_keys.append('file:'+content_hash(prompt))
            files[path]=(await content_call(book_id,config,prompt))['content']
        chapter_map,topic_index,chapter_rows,topic_rows=build_indexes(chapters,analyses,chapter_topics)
        files['chapter-map.md']=chapter_map;files['topic-index.md']=topic_index
        name='book-'+book_id[:8]
        files['SKILL.md']=build_master(b,name,core,chapter_rows,topic_rows,files)
        try:quality=validate_package(files)
        except ValueError:
            for key in [core_key,*file_keys]:discard(book_id,key)
            raise
        metadata={'skillVersion':'2.0','generatorVersion':GENERATOR_VERSION,'generatorReference':REFERENCE,
            'model':config.model,'generatedAt':db.now(),'bookHash':b['fileHash'],'title':b['title'],
            'author':b['author'],'chapterCount':len(chapters),'language':b['language'],'kind':kind,'name':name,'purpose':purpose,
            'depth':depth,'chapterTokenTarget':chapter_budget(kind,depth),'quality':quality,'exportPolicy':'distilled-by-default'}
        files['metadata.json']=json.dumps(metadata,ensure_ascii=False,indent=2)
        # Full source is private evidence, not a distilled chapter. It is only
        # exported when the user explicitly chooses an archive including source.
        for i,ch in enumerate(chapters):files[f'references/chapter-{i+1:03}.md']='# '+ch['title']+'\n\n'+ch['content']
        db.update_book(book_id,progress=95,stage='校验 Skill 预算与索引，构建原文检索')
        folder=db.DATA/'skills'/book_id;staging=db.DATA/'skills'/(book_id+'.pending')
        shutil.rmtree(staging,ignore_errors=True);staging.mkdir(parents=True,exist_ok=True)
        for path,content in files.items():
            target=staging/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content,encoding='utf-8')
        with db.connect() as c:
            c.execute('DELETE FROM skill_files WHERE bookId=?',(book_id,))
            for path,content in files.items():c.execute('INSERT INTO skill_files VALUES(?,?,?,?)',(db.uid(),book_id,path,content))
            c.execute('INSERT OR REPLACE INTO skills VALUES(?,?)',(book_id,json.dumps(metadata,ensure_ascii=False)))
        index_book(book_id);index_skills(book_id)
        shutil.rmtree(folder,ignore_errors=True);staging.rename(folder)
        questions=core.get('questions',{})
        questions={k:[q for q in v if isinstance(q,str)][:8] for k,v in questions.items() if isinstance(v,list)} if isinstance(questions,dict) else {}
        db.update_book(book_id,status='ready',progress=100,stage='Book Skill 已准备就绪',questions=json.dumps(questions,ensure_ascii=False),error='')
    except asyncio.CancelledError:
        db.update_book(book_id,status='paused',stage='已暂停 · 可从已保存的知识继续');raise
    except Exception as e:
        safe=str(e) if isinstance(e,(llm.LLMError,ValueError)) else '生成失败，请检查模型连接并继续生成'
        db.update_book(book_id,status='failed',error=safe,stage='生成中断 · 章节分析与知识文件已保存')
    finally:TASKS.pop(book_id,None)

def start(book_id,config,purpose='all'):
    if book_id in TASKS and not TASKS[book_id].done():raise ValueError('本书正在生成中')
    TASKS[book_id]=asyncio.create_task(generate_skill(book_id,config,purpose))
