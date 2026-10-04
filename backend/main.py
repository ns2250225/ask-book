import asyncio, json, io, zipfile, shutil, hashlib, re
from pathlib import Path
from typing import Literal
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from backend import storage as db, llm
from backend.book_to_skill import parser, worker, retrieval
from backend.agent import answer
from backend.book_to_skill.demo import upgrade_demo

@asynccontextmanager
async def lifespan(app):
    db.init()
    for demo_book in db.rows("SELECT id FROM books WHERE fileType='demo'"):upgrade_demo(demo_book['id'])
    db.execute("UPDATE books SET status='paused',stage='服务重启 · 可继续生成' WHERE status='generating'")
    yield
    tasks=list(worker.TASKS.values())
    for task in tasks: task.cancel()
    if tasks: await asyncio.gather(*tasks,return_exceptions=True)

app=FastAPI(title='问书 BookSkill API',lifespan=lifespan,docs_url='/api/docs',redoc_url='/api/redoc',openapi_url='/api/openapi.json')

def require(book_id):
    b=db.book(book_id)
    if not b: raise HTTPException(404,'书籍不存在')
    return b

def require_conversation(book_id,cid):
    row=db.one('SELECT * FROM conversations WHERE id=? AND bookId=?',(cid,book_id))
    if not row: raise HTTPException(404,'对话不存在')
    return row

@app.get('/api/health')
def health(): return {'status':'ok','generatorVersion':worker.GENERATOR_VERSION,'generatorReference':worker.REFERENCE}

@app.get('/api/books')
def list_books(): return [db.book(b['id']) for b in db.rows('SELECT id FROM books ORDER BY createdAt DESC')]

@app.post('/api/books')
async def upload(file:UploadFile=File(...)):
    name=file.filename or 'book.txt'; ext=Path(name).suffix.lower()
    if ext not in ('.epub','.pdf','.txt','.md','.markdown'): raise HTTPException(400,'支持 EPUB / PDF / TXT / Markdown')
    content=await file.read(parser.MAX_BYTES+1)
    if len(content)>parser.MAX_BYTES: raise HTTPException(413,'电子书不能超过 50 MB')
    if not content: raise HTTPException(400,'文件为空')
    digest=hashlib.sha256(content).hexdigest()
    existing=db.one('SELECT id FROM books WHERE fileHash=?',(digest,))
    if existing: return {'book':db.book(existing['id']),'duplicate':True,'estimate':worker.estimate(existing['id'])}
    bid=db.uid(); folder=db.DATA/'books'/bid; folder.mkdir(parents=True)
    path=folder/('original'+ext); path.write_bytes(content)
    try: parsed=await asyncio.to_thread(parser.parse,path,name)
    except Exception as e:
        shutil.rmtree(folder,ignore_errors=True)
        raise HTTPException(400,str(e) if isinstance(e,ValueError) else '电子书解析失败，文件可能损坏、加密或不兼容')
    try:
        with db.connect() as c:
            c.execute('INSERT INTO books(id,title,author,language,fileType,fileHash,status,createdAt,progress,stage,cover,stats) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(bid,parsed['title'],parsed['author'],parsed['language'],ext[1:],digest,'parsed',db.now(),5,'电子书解析完成',parsed['cover'],json.dumps({'pages':parsed['pages']})))
            for i,ch in enumerate(parsed['chapters']): c.execute('INSERT INTO chapters VALUES(?,?,?,?,?)',(db.uid(),bid,i,ch['title'],ch['content']))
        (folder/'parsed.json').write_text(json.dumps(parsed,ensure_ascii=False),encoding='utf-8')
        retrieval.index_book(bid)
    except Exception:
        db.execute('DELETE FROM books WHERE id=?',(bid,)); shutil.rmtree(folder,ignore_errors=True); raise
    return {'book':db.book(bid),'estimate':worker.estimate(bid),'duplicate':False}

@app.get('/api/books/{bid}')
def get_book(bid:str): return require(bid)

@app.patch('/api/books/{bid}')
def edit_book(bid:str,body:dict):
    require(bid)
    values={k:str(v).strip()[:300] for k,v in body.items() if k in ('title','author')}
    if not values or not values.get('title',True): raise HTTPException(400,'书名不能为空')
    db.update_book(bid,**values); return require(bid)

@app.delete('/api/books/{bid}')
async def delete_book(bid:str):
    require(bid)
    if bid in worker.TASKS:
        task=worker.TASKS[bid]; task.cancel(); await asyncio.gather(task,return_exceptions=True)
    with db.connect() as c:
        c.execute('DELETE FROM passage_fts WHERE bookId=?',(bid,)); c.execute('DELETE FROM skill_fts WHERE bookId=?',(bid,)); c.execute('DELETE FROM books WHERE id=?',(bid,))
    for base in ('books','skills'): shutil.rmtree(db.DATA/base/bid,ignore_errors=True)
    return {'ok':True}

@app.get('/api/books/{bid}/estimate')
def estimate(bid:str,purpose:Literal['all','apply','think','reference']='all'): require(bid); return worker.estimate(bid,purpose)

class GenerateRequest(BaseModel):
    config:llm.Config
    reset:bool=False
    purpose:Literal['all','apply','think','reference']='all'

@app.post('/api/books/{bid}/generate')
async def generate(bid:str,body:GenerateRequest):
    require(bid)
    if bid in worker.TASKS: raise HTTPException(409,'正在生成中')
    if not db.one('SELECT id FROM chapters WHERE bookId=?',(bid,)): raise HTTPException(400,'此 Skill 没有原始章节，无法重新生成')
    if body.reset: db.execute('DELETE FROM checkpoints WHERE bookId=?',(bid,))
    db.update_book(bid,status='generating',stage='准备知识蒸馏',error='')
    worker.start(bid,body.config,body.purpose); return {'ok':True}

@app.post('/api/books/{bid}/pause')
async def pause(bid:str):
    require(bid)
    task=worker.TASKS.get(bid)
    if task: task.cancel(); await asyncio.gather(task,return_exceptions=True)
    return require(bid)

@app.get('/api/books/{bid}/chapters')
def chapters(bid:str): require(bid); return db.rows('SELECT id,title,idx,length(content) chars FROM chapters WHERE bookId=? ORDER BY idx',(bid,))

@app.get('/api/books/{bid}/chapters/{cid}')
def chapter(bid:str,cid:str):
    require(bid); ch=db.one('SELECT * FROM chapters WHERE bookId=? AND id=?',(bid,cid))
    if not ch: raise HTTPException(404,'章节不存在')
    return ch

@app.get('/api/books/{bid}/skill')
def skill(bid:str):
    require(bid)
    return {'files':db.rows('SELECT path,length(content) chars FROM skill_files WHERE bookId=? ORDER BY path',(bid,)),'metadata':db.book(bid)['metadata']}

@app.get('/api/books/{bid}/skill/file')
def skill_file(bid:str,path:str):
    require(bid); f=db.one('SELECT path,content FROM skill_files WHERE bookId=? AND path=?',(bid,path))
    if not f: raise HTTPException(404,'文件不存在')
    return f

@app.get('/api/books/{bid}/search')
def search(bid:str,q:str,kind:str='skill'):
    require(bid)
    if kind not in ('skill','book'): raise HTTPException(400,'无效检索类型')
    return retrieval.search(bid,q,kind,20)

@app.get('/api/books/{bid}/export')
def export(bid:str,include_source:bool=False):
    b=require(bid); files=db.rows('SELECT path,content FROM skill_files WHERE bookId=?',(bid,))
    if not files: raise HTTPException(400,'请先生成 Skill')
    buff=io.BytesIO(); name=(b['metadata'] or {}).get('name','book-'+bid[:8]); name=re.sub(r'[^a-zA-Z0-9_-]','-',name)[:80] or 'book'
    with zipfile.ZipFile(buff,'w',zipfile.ZIP_DEFLATED) as z:
        for f in files:
            if not include_source and f['path'].startswith('references/'):continue
            z.writestr(name+'/'+f['path'],f['content'])
        z.writestr(name+'/book.json',json.dumps({'title':b['title'],'author':b['author'],'language':b['language'],'kind':b['kind'],'questions':b['questions'],'stats':b['stats'],'includesSource':include_source,'chapters':db.rows('SELECT title,content FROM chapters WHERE bookId=? ORDER BY idx',(bid,)) if include_source else []},ensure_ascii=False))
    return StreamingResponse(iter([buff.getvalue()]),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="{name}.skill.zip"'})

@app.post('/api/skills/import')
async def import_skill(file:UploadFile=File(...)):
    raw=await file.read(parser.MAX_BYTES+1)
    if len(raw)>parser.MAX_BYTES: raise HTTPException(413,'Skill ZIP 不能超过 50 MB')
    try:
        files={}
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos=z.infolist()
            if len(infos)>2000 or sum(x.file_size for x in infos)>200*1024*1024: raise ValueError('Skill 解压内容超过限制')
            names=[x.filename for x in infos if not x.is_dir()]
            root=next((n[:-len('SKILL.md')] for n in names if n.endswith('SKILL.md')),None)
            if root is None: raise ValueError('ZIP 中缺少 SKILL.md')
            for info in infos:
                if info.is_dir() or not info.filename.startswith(root): continue
                rel=info.filename[len(root):]
                if not rel or rel.startswith('/') or '\\' in rel or '..' in Path(rel).parts: raise ValueError('Skill 包含不安全文件路径')
                if not rel.endswith(('.md','.json')): continue
                if info.file_size>20*1024*1024: raise ValueError('Skill 单个文件过大')
                files[rel]=z.read(info).decode('utf-8')
        if not files.get('SKILL.md','').strip(): raise ValueError('SKILL.md 不能为空')
        meta=json.loads(files.get('metadata.json','{}')); info=json.loads(files.get('book.json','{}'))
        if not isinstance(meta,dict) or not isinstance(info,dict): raise ValueError('元数据格式无效')
        master=files['SKILL.md']
        heading=re.search(r'^#\s+(.+)$',master,re.M)
        front_name=re.search(r'^name:\s*[\"\']?([a-z0-9-]+)',master,re.M)
        author_line=re.search(r'(?:\*\*Author\*\*|作者)\s*[:：]\s*([^|\n]+)',master)
        if front_name and not meta.get('name'):meta['name']=front_name[1]
        if author_line and not meta.get('author'):meta['author']=author_line[1].strip()
        bid=db.uid(); title=str(info.get('title',meta.get('title',heading[1] if heading else '导入的 Book Skill')))[:300]
        statistics=info.get('stats',{})
        if not isinstance(statistics,dict) or any(not isinstance(v,(int,float)) for v in statistics.values()): raise ValueError('统计格式无效')
        questions=info.get('questions',{})
        if not isinstance(questions,dict) or any(not isinstance(v,list) or any(not isinstance(q,str) for q in v) for v in questions.values()): raise ValueError('推荐问题格式无效')
        chapter_items=info.get('chapters',[])
        if not chapter_items:
            chapter_items=[{'title':v.splitlines()[0].lstrip('# ').strip() or k,'content':'\n'.join(v.splitlines()[1:])} for k,v in files.items() if k.startswith('references/')]
        if not isinstance(chapter_items,list): raise ValueError('章节格式无效')
        for item in chapter_items:
            if not isinstance(item,dict) or not isinstance(item.get('content'),str): raise ValueError('章节格式无效')
        meta.update({'name':str(meta.get('name','book-'+bid[:8])),'title':title})
        with db.connect() as c:
            c.execute('INSERT INTO books(id,title,author,language,fileType,fileHash,status,createdAt,progress,stage,kind,questions,stats) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(bid,title,str(info.get('author',meta.get('author','未知作者'))),str(info.get('language','zh')),'skill',hashlib.sha256(raw).hexdigest(),'ready',db.now(),100,'Skill 导入完成',str(info.get('kind',meta.get('kind','其他'))),json.dumps(info.get('questions',{}),ensure_ascii=False),json.dumps(statistics,ensure_ascii=False)))
            c.execute('INSERT INTO skills VALUES(?,?)',(bid,json.dumps(meta,ensure_ascii=False)))
            for path,content in files.items():
                if path!='book.json': c.execute('INSERT INTO skill_files VALUES(?,?,?,?)',(db.uid(),bid,path,content))
            for i,ch in enumerate(chapter_items): c.execute('INSERT INTO chapters VALUES(?,?,?,?,?)',(db.uid(),bid,i,str(ch.get('title',f'章节 {i+1}')),ch['content']))
        retrieval.index_book(bid); retrieval.index_skills(bid)
        return require(bid)
    except (ValueError,zipfile.BadZipFile,UnicodeDecodeError,RuntimeError) as e: raise HTTPException(400,str(e) if isinstance(e,ValueError) else '无效或加密的 Skill ZIP 文件')

@app.post('/api/settings/test')
async def test_connection(config:llm.Config):
    try:
        m=await llm.chat(config,[{'role':'user','content':'只回复 OK'}],max_tokens=256)
        return {'ok':True,'message':m.get('content','连接成功')}
    except llm.LLMError as e: raise HTTPException(400,str(e))

@app.get('/api/books/{bid}/conversations')
def conversations(bid:str): require(bid); return db.rows('SELECT * FROM conversations WHERE bookId=? ORDER BY updatedAt DESC',(bid,))

class Title(BaseModel): title:str=Field(min_length=1,max_length=200)

@app.post('/api/books/{bid}/conversations')
def create_conversation(bid:str,body:Title):
    require(bid); cid=db.uid(); stamp=db.now(); db.execute('INSERT INTO conversations VALUES(?,?,?,?,?)',(cid,bid,body.title,stamp,stamp)); return require_conversation(bid,cid)

@app.patch('/api/books/{bid}/conversations/{cid}')
def rename_conversation(bid:str,cid:str,body:Title):
    require_conversation(bid,cid); db.execute('UPDATE conversations SET title=?,updatedAt=? WHERE id=?',(body.title,db.now(),cid)); return {'ok':True}

@app.delete('/api/books/{bid}/conversations/{cid}')
def delete_conversation(bid:str,cid:str):
    require_conversation(bid,cid); db.execute('DELETE FROM conversations WHERE id=?',(cid,)); return {'ok':True}

@app.get('/api/books/{bid}/conversations/{cid}/messages')
def messages(bid:str,cid:str):
    require_conversation(bid,cid); ms=db.rows('SELECT * FROM messages WHERE conversationId=? ORDER BY createdAt',(cid,))
    for m in ms: m['references']=json.loads(m.pop('refs'))
    return ms

class Ask(BaseModel):
    question:str=Field(min_length=1,max_length=12000)
    config:llm.Config
    otherBookIds:list[str]=Field(default_factory=list,max_length=4)

ACTIVE_CHATS=set()

@app.post('/api/books/{bid}/conversations/{cid}/ask')
async def ask(bid:str,cid:str,body:Ask):
    b=require(bid); conv=require_conversation(bid,cid)
    if b['status']!='ready': raise HTTPException(400,'请先生成 Book Skill')
    for other in body.otherBookIds:
        if require(other)['status']!='ready': raise HTTPException(400,'选中的书尚未生成 Skill')
    if cid in ACTIVE_CHATS: raise HTTPException(409,'此对话正在回答，请等待完成')
    ACTIVE_CHATS.add(cid)
    mid=db.uid()
    try: db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?)',(mid,cid,'user',body.question,'[]',db.now()))
    except Exception:
        ACTIVE_CHATS.discard(cid)
        raise
    if conv['title']=='新的对话': db.execute('UPDATE conversations SET title=? WHERE id=?',(body.question[:30],cid))
    async def stream():
        try:
            async for event in answer(bid,cid,body.question,body.config,body.otherBookIds): yield json.dumps(event,ensure_ascii=False)+'\n'
        except llm.LLMError as e: yield json.dumps({'type':'error','message':str(e)},ensure_ascii=False)+'\n'
        except Exception: yield json.dumps({'type':'error','message':'问书服务出错，请稍后重试'},ensure_ascii=False)+'\n'
        finally: ACTIVE_CHATS.discard(cid)
    return StreamingResponse(stream(),media_type='application/x-ndjson')

@app.get('/api/books/{bid}/notes')
def notes(bid:str): require(bid); return db.rows('SELECT * FROM notes WHERE bookId=? ORDER BY createdAt DESC',(bid,))

class Note(BaseModel): content:str=Field(min_length=1,max_length=50000)

@app.post('/api/books/{bid}/notes')
def save_note(bid:str,body:Note):
    require(bid); nid=db.uid(); db.execute('INSERT INTO notes VALUES(?,?,?,?)',(nid,bid,body.content,db.now())); return {'id':nid}

@app.delete('/api/books/{bid}/notes/{nid}')
def delete_note(bid:str,nid:str):
    require(bid); db.execute('DELETE FROM notes WHERE bookId=? AND id=?',(bid,nid)); return {'ok':True}

# Local authored example, clearly labelled; no AI-generated claims or copyrighted source.
@app.post('/api/demo')
def demo():
    existing=db.one("SELECT id FROM books WHERE fileHash='demo-reading-v1'")
    if existing:
        upgrade_demo(existing['id']);return require(existing['id'])
    bid=db.uid(); stamp=db.now(); title='阅读的复利 · 功能示例'
    texts=[('第一章 · 给知识一个位置','阅读的价值不在于读过多少页，而在于留下了多少可以再次使用的知识。阅读之后，先用自己的话总结一个概念，再为它找一个实际问题。知识需要上下文：记录观点来自哪里，适用于什么条件，以及有什么局限。'),('第二章 · 从理解到行动','把一个观点转化成行动时，选择足够小的步骤。每天记录一个问题，试用一个方法，再观察结果。每周复盘一次，比较原先的预期与实际结果。复盘不是评价自己，而是改善下一次行动。'),('第三章 · 保持批判','书中的观点有它的适用条件。区分作者的事实陈述、推理和建议，检查证据与假设。跨书比较时，先确认两位作者是否在讨论相同的问题。不要把有说服力的叙述直接当作普遍规律。')]
    files={'SKILL.md':'---\nname: reading-compound\ndescription: 阅读实践示例知识 Skill\n---\n# 阅读的复利\n这是问书自编的功能示例。优先阅读 overview、concepts、methods，并引用真实章节。','overview.md':'# 阅读的复利\n\n这是问书团队自编的功能演示文本，非真实出版书籍。\n\n阅读的三个环节：整理知识（第一章）、实践与复盘（第二章）、批判性验证（第三章）。','concepts.md':'# 核心概念\n\n## 可复用知识\n用自己的话总结概念并绑定实际问题，保留出处、条件与局限。（第一章）\n\n## 反馈循环\n通过小步实践与每周复盘，改善后续行动。（第二章）\n\n## 批判阅读\n检查事实、推理、建议、证据与隐含假设。（第三章）','methods.md':'# 实践方法\n\n1. 每天记一个问题，试一个方法。（第二章）\n2. 每周比较预期与实际结果，改善下次行动。（第二章）\n3. 比较不同作者前先确认问题是否相同。（第三章）','arguments.md':'# 主要论点\n\n阅读价值取决于可再次使用的知识，而非页数。（第一章）\n有说服力的叙述并非普遍规律。（第三章）','chapter-map.md':'# 章节地图\n\n第一章：整理知识。\n第二章：实践反馈。\n第三章：检查证据与假设。'}
    meta={'name':'reading-compound','skillVersion':'1.0','generatorVersion':'demo-authored','model':'人工编写 · 示例','generatedAt':stamp,'bookHash':'demo-reading-v1','title':title,'author':'问书 · 示例文本'}
    files['metadata.json']=json.dumps(meta,ensure_ascii=False)
    questions={'快速了解':['这本书的核心思想是什么？','三个章节之间有什么联系？'],'深入理解':['为什么知识需要上下文？','复盘和评价自己的区别是什么？'],'实际应用':['帮我制定一个七天阅读实践计划。','把这本书转化为每日 Checklist。'],'批判阅读':['这个阅读方法有什么局限？','哪些观点需要更多证据？']}
    with db.connect() as c:
        c.execute('INSERT INTO books(id,title,author,language,fileType,fileHash,status,createdAt,progress,stage,kind,questions,stats) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(bid,title,'问书 · 示例文本','zh','demo','demo-reading-v1','ready',stamp,100,'人工编写的功能示例','其他',json.dumps(questions,ensure_ascii=False),json.dumps({'concepts':3,'methods':3,'arguments':2,'chapters':3})))
        c.execute('INSERT INTO skills VALUES(?,?)',(bid,json.dumps(meta,ensure_ascii=False)))
        for i,(t,content) in enumerate(texts):
            c.execute('INSERT INTO chapters VALUES(?,?,?,?,?)',(db.uid(),bid,i,t,content)); files[f'references/chapter-{i+1:03}.md']='# '+t+'\n\n'+content
        for p,content in files.items(): c.execute('INSERT INTO skill_files VALUES(?,?,?,?)',(db.uid(),bid,p,content))
    retrieval.index_book(bid);retrieval.index_skills(bid);upgrade_demo(bid);return require(bid)

DIST=Path(__file__).resolve().parent.parent/'frontend'/'dist'
if DIST.exists():
    app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='assets')
    @app.get('/{path:path}')
    def spa(path:str):
        if path.startswith('api/'): raise HTTPException(404,'接口不存在')
        return FileResponse(DIST/'index.html')
