import asyncio,io,json,zipfile
import pytest
from fastapi.testclient import TestClient
from backend import storage as db,llm
from backend.main import app
from backend.book_to_skill import worker,parser,retrieval

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DATA',tmp_path)
    monkeypatch.setattr(db,'DB',tmp_path/'test.db')
    with TestClient(app) as c: yield c

CONFIG={'baseURL':'http://127.0.0.1:9999/v1','apiKey':'SECRET_NOT_PERSISTED','model':'test-model','temperature':.3,'maxTokens':4096}
TEXT='# 测试阅读\n\n## 第一章 知识\n知识需要上下文。保留知识的来源、适用条件与局限。\n\n## 第二章 实践\n每天实践一个方法。每周反思行动的结果。'

def upload(client):
    r=client.post('/api/books',files={'file':('reading.md',TEXT.encode(),'text/markdown')});assert r.status_code==200,r.text
    return r.json()['book']['id']

def test_upload_formats_and_search(client,tmp_path):
    bid=upload(client)
    b=client.get('/api/books/'+bid).json();assert b['title']=='测试阅读';assert b['chapterCount']==2
    assert client.post('/api/books',files={'file':('other.md',TEXT.encode())}).json()['duplicate']
    result=client.get(f'/api/books/{bid}/search',params={'q':'知识来源','kind':'book'}).json();assert result;assert result[0]['chapter']=='第一章 知识'
    ch=client.get(f'/api/books/{bid}/chapters/{result[0]["chapterId"]}').json()
    assert ch['content'][result[0]['start']:result[0]['end']]==result[0]['text']
    r=client.post('/api/books',files={'file':('gbk.txt','第一章 测试\n这是中文正文与阅读知识。'.encode('gb18030'))});assert r.status_code==200
    assert client.post('/api/books',files={'file':('bad.exe',b'bad')}).status_code==400
    assert client.post('/api/books',files={'file':('blank.txt',b'')}).status_code==400
    import pymupdf as fitz
    document=fitz.open();page=document.new_page();page.insert_text((50,80),'Chapter 1\nReadable PDF knowledge. '*12)
    raw=document.tobytes();document.close()
    assert client.post('/api/books',files={'file':('book.pdf',raw)}).status_code==200
    document=fitz.open();document.new_page();raw=document.tobytes();document.close()
    r=client.post('/api/books',files={'file':('scan.pdf',raw)});assert r.status_code==400;assert '扫描' in r.json()['detail']
    from ebooklib import epub
    book=epub.EpubBook();book.set_identifier('test');book.set_title('EPUB 测试');book.set_language('zh');book.add_author('作者')
    chapter=epub.EpubHtml(title='目录章节',file_name='one.xhtml',lang='zh');chapter.content='<h1>目录章节</h1><p>阅读知识与实践需要上下文和明确的使用场景。这是足够长的测试正文。</p>'
    book.add_item(chapter);book.toc=(chapter,);book.add_item(epub.EpubNcx());book.add_item(epub.EpubNav());book.spine=['nav',chapter]
    path=tmp_path/'epub.epub';epub.write_epub(str(path),book)
    r=client.post('/api/books',files={'file':('test.epub',path.read_bytes())});assert r.status_code==200,r.text;assert r.json()['book']['author']=='作者'

@pytest.mark.asyncio
async def test_generation_checkpoint_resume_and_key_security(client,monkeypatch):
    bid=upload(client);calls=[]
    async def fake(config,prompt,system=''):
        calls.append(prompt)
        if '判断书籍类型' in prompt:return {'kind':'商业'}
        if '生成 Skill 的核心知识层' in prompt:
            return {'core':'### 上下文框架\n当复用知识时，先确认来源、条件与局限（第一章）。','voice':'先确认依据，再讨论应用。','scope':'只覆盖这份阅读文本。','questions':{'快速了解':['核心知识是什么？']}}
        if '生成按需加载的蒸馏知识' in prompt:
            return {'content':'# 章节知识\n\n## 核心思想\n知识需要上下文。\n\n## 框架与适用条件\n复用知识前先检查来源与条件（第一章）。','topics':['上下文']}
        if '返回 {"content":"Markdown"}' in prompt:
            return {'content':'# 知识工具\n\n当复用知识时，先确认来源与条件，因为观点有适用边界（第一章）。'}
        return {'summary':'知识与实践','concepts':[{'name':'上下文','description':'保留知识来源','chapter':'第一章'}],'methods':[{'name':'实践','description':'每天练习'}],'arguments':[],
                'frameworks':[{'name':'上下文框架','when':'复用知识时','how':['核对来源','确认条件'],'chapter':'第一章'}],
                'decision_rules':[{'name':'检查来源','condition':'准备应用知识','action':'核对条件','reason':'避免误用','chapter':'第一章'}]}
    monkeypatch.setattr(llm,'json_chat',fake)
    await worker.generate_skill(bid,llm.Config(**CONFIG))
    assert db.book(bid)['status']=='ready',db.book(bid)
    count=len(calls);assert count>=5
    await worker.generate_skill(bid,llm.Config(**CONFIG));assert len(calls)==count
    assert retrieval.search(bid,'上下文','skill')
    files=db.rows('SELECT path FROM skill_files WHERE bookId=?',(bid,));assert any(x['path']=='SKILL.md' for x in files);assert any(x['path'].startswith('references/') for x in files)
    assert sum(x['path'].startswith('chapters/') for x in files)==2
    assert {'patterns.md','cheatsheet.md','topic-index.md'}.issubset({x['path'] for x in files})
    metadata=db.book(bid)['metadata'];assert metadata['generatorReference']['repository'].endswith('virgiliojr94/book-to-skill')
    assert metadata['quality']['masterTokens']<=4000
    master=db.one("SELECT content FROM skill_files WHERE bookId=? AND path='SKILL.md'",(bid,))['content']
    assert '上下文框架' in master;assert '(chapters/ch001.md)' in master
    assert 'type: book' not in master
    assert b'SECRET_NOT_PERSISTED' not in db.DB.read_bytes()
    for f in db.DATA.rglob('*'):
        if f.is_file():assert b'SECRET_NOT_PERSISTED' not in f.read_bytes()

@pytest.mark.asyncio
async def test_interruption_preserves_checkpoint(client,monkeypatch):
    bid=upload(client);calls=0
    async def interrupted(config,prompt,system=''):
        nonlocal calls
        calls+=1
        if calls==3:raise llm.LLMError('401 · API Key 无效')
        return {'kind':'其他','summary':'上下文','concepts':[]}
    monkeypatch.setattr(llm,'json_chat',interrupted)
    await worker.generate_skill(bid,llm.Config(**CONFIG))
    assert db.book(bid)['status']=='failed'
    assert db.one('SELECT count(*) n FROM checkpoints WHERE bookId=?',(bid,))['n']==2
    assert db.book(bid)['progress']<100


def test_import_export_cascade_and_zip_safety(client):
    bid=client.post('/api/demo').json()['id']
    default=client.get(f'/api/books/{bid}/export').content
    with zipfile.ZipFile(io.BytesIO(default)) as z:
        assert not any('/references/' in n for n in z.namelist())
        info=json.loads(z.read(next(n for n in z.namelist() if n.endswith('book.json'))))
        assert info['chapters']==[];assert not info['includesSource']
    raw=client.get(f'/api/books/{bid}/export',params={'include_source':'true'}).content
    with zipfile.ZipFile(io.BytesIO(raw)) as z:assert any(n.endswith('SKILL.md') for n in z.namelist())
    imported=client.post('/api/skills/import',files={'file':('example.skill.zip',raw)})
    assert imported.status_code==200,imported.text
    new_id=imported.json()['id'];assert imported.json()['chapterCount']==3
    assert client.get(f'/api/books/{new_id}/search',params={'q':'批判','kind':'book'}).json()
    buff=io.BytesIO()
    with zipfile.ZipFile(buff,'w') as z:z.writestr('x/SKILL.md','# Test');z.writestr('x/../../evil.md','bad')
    assert client.post('/api/skills/import',files={'file':('bad.zip',buff.getvalue())}).status_code==400
    conv=client.post(f'/api/books/{bid}/conversations',json={'title':'会话'}).json()
    client.post(f'/api/books/{bid}/notes',json={'content':'笔记'})
    assert client.delete(f'/api/books/{bid}').status_code==200
    assert not db.rows('SELECT * FROM chapters WHERE bookId=?',(bid,));assert not db.rows('SELECT * FROM conversations WHERE id=?',(conv['id'],));assert not db.rows('SELECT * FROM passage_fts WHERE bookId=?',(bid,));assert not db.rows('SELECT * FROM skill_fts WHERE bookId=?',(bid,))
    assert client.get(f'/api/books/{bid}').status_code==404


def test_agent_tool_calls_and_citation_validation(client,monkeypatch):
    bid=client.post('/api/demo').json()['id'];cid=client.post(f'/api/books/{bid}/conversations',json={'title':'新的对话'}).json()['id'];calls=[]
    async def fake(config,messages,tools=None,max_tokens=None):
        calls.append(messages.copy())
        if len(calls)==1:return {'role':'assistant','content':None,'tool_calls':[{'id':'call-1','type':'function','function':{'name':'search_book','arguments':'{"query":"知识"}'}}]}
        return {'role':'assistant','content':'## 根据本书\n知识需要上下文。[1]\n无效引用应移除。[999]\n\n## 我的分析\n可把知识用于练习。'}
    monkeypatch.setattr(llm,'chat',fake)
    response=client.post(f'/api/books/{bid}/conversations/{cid}/ask',json={'question':'知识为什么需要上下文？','config':CONFIG})
    assert response.status_code==200
    events=[json.loads(s) for s in response.text.splitlines()];answer=next(e for e in events if e['type']=='answer')['message'];assert answer['references'];assert '[999]' not in answer['content'];assert any(m['role']=='tool' for m in calls[-1])
    ms=client.get(f'/api/books/{bid}/conversations/{cid}/messages').json();assert [m['role'] for m in ms]==['user','assistant']
    assert client.patch(f'/api/books/{bid}/conversations/{cid}',json={'title':'上下文问题'}).status_code==200
    assert client.get(f'/api/books/{bid}/conversations').json()[0]['title']=='上下文问题'
    other=upload(client);assert client.get(f'/api/books/{other}/conversations/{cid}/messages').status_code==404


def test_provider_error_and_context_fallback(client,monkeypatch):
    bid=client.post('/api/demo').json()['id'];cid=client.post(f'/api/books/{bid}/conversations',json={'title':'新的对话'}).json()['id'];calls=[]
    async def fake(config,messages,tools=None,max_tokens=None):
        calls.append(messages)
        if len(calls)==1:raise llm.LLMError('400 · 请求参数或上下文长度不被模型接受')
        assert any('我的问题是什么' in str(m.get('content','')) for m in messages)
        return {'role':'assistant','content':'根据本书：阅读需要实践。'}
    monkeypatch.setattr(llm,'chat',fake)
    r=client.post(f'/api/books/{bid}/conversations/{cid}/ask',json={'question':'我的问题是什么','config':CONFIG})
    assert any(json.loads(s)['type']=='answer' for s in r.text.splitlines());assert len(calls)==2
    async def failure(*args,**kwargs):raise llm.LLMError('401 · API Key 无效')
    monkeypatch.setattr(llm,'chat',failure)
    r=client.post('/api/settings/test',json=CONFIG);assert r.status_code==400;assert 'SECRET' not in r.text
    r=client.post(f'/api/books/{bid}/conversations/{cid}/ask',json={'question':'再问一次','config':CONFIG});assert '"type": "error"' in r.text


def test_long_book_sections_preserve_every_character():
    text=('长段落 '*10000)+'\n\n'+('another line\n'*10000)
    split=parser.sections(text,10000);assert ''.join(split)==text;assert max(map(len,split))<=10000

@pytest.mark.asyncio
async def test_gateway_openai_wire_format_and_errors(monkeypatch):
    import httpx
    real=httpx.AsyncClient;requests=[]
    def respond(request):
        requests.append(request)
        assert request.url.path=='/v1/chat/completions'
        payload=json.loads(request.content)
        assert payload['model']=='test-model';assert payload['max_tokens']==256
        assert request.headers['Authorization']=='Bearer SECRET_NOT_PERSISTED'
        return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':'OK'}}]})
    transport=httpx.MockTransport(respond)
    monkeypatch.setattr(llm.httpx,'AsyncClient',lambda **kwargs:real(transport=transport,**kwargs))
    message=await llm.chat(llm.Config(**CONFIG),[{'role':'user','content':'测试连接'}],max_tokens=256)
    assert message['content']=='OK';assert len(requests)==1
    transport=httpx.MockTransport(lambda _:httpx.Response(401,json={'error':{'message':'secret body SECRET_NOT_PERSISTED'}}))
    monkeypatch.setattr(llm.httpx,'AsyncClient',lambda **kwargs:real(transport=transport,**kwargs))
    with pytest.raises(llm.LLMError) as caught:await llm.chat(llm.Config(**CONFIG),[{'role':'user','content':'test'}])
    assert '401' in str(caught.value);assert 'SECRET' not in str(caught.value)


def test_archive_minimal_external_skill(client):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:
        z.writestr('external/SKILL.md','---\nname: external\ndescription: 测试\n---\n# 一个外部 Skill')
        z.writestr('external/references/chapter-01.md','# 测试章节\n\n  原文保留空格，并可精确追溯。')
    r=client.post('/api/skills/import',files={'file':('external.skill.zip',buffer.getvalue())});assert r.status_code==200,r.text
    bid=r.json()['id'];matches=client.get(f'/api/books/{bid}/search',params={'q':'空格','kind':'book'}).json();assert matches
    chapter=client.get(f'/api/books/{bid}/chapters/{matches[0]["chapterId"]}').json()
    assert chapter['content'][matches[0]['start']:matches[0]['end']]==matches[0]['text']
    assert client.get('/api/docs').status_code==200


def test_pause_api_and_server_restart_recovery(client,monkeypatch):
    bid=upload(client)
    async def slow(*args,**kwargs):
        await asyncio.sleep(30)
        return {'kind':'其他'}
    monkeypatch.setattr(llm,'json_chat',slow)
    response=client.post(f'/api/books/{bid}/generate',json={'config':CONFIG});assert response.status_code==200
    assert client.post(f'/api/books/{bid}/generate',json={'config':CONFIG}).status_code==409
    assert client.post(f'/api/books/{bid}/pause').json()['status']=='paused'
    assert bid not in worker.TASKS
    assert b'SECRET_NOT_PERSISTED' not in db.DB.read_bytes()

@pytest.mark.asyncio
async def test_optional_embedding_hybrid_search(client,monkeypatch):
    from backend.agent import hybrid
    bid=client.post('/api/demo').json()['id']
    async def vectors(config,texts):return [[1.,0.] for _ in texts]
    monkeypatch.setattr(llm,'embeddings',vectors)
    config=llm.Config(**CONFIG,embeddingModel='test-embedding')
    values=await hybrid(bid,'实践','skill',config)
    assert values;assert 'hybridScore' in values[0]
    assert all(not f['path'].startswith('references/') for f in values)


def test_book_to_skill_budgets_and_index_integrity():
    from backend.book_to_skill.builder import build_master,build_indexes,validate_package,bounded_context,merge_analysis
    from backend.book_to_skill.spec import chapter_budget,depth_for
    assert chapter_budget('技术',depth_for('all'))==3000
    assert chapter_budget('技术',depth_for('reference'))==1800
    assert chapter_budget('商业',depth_for('all'))==1800
    assert chapter_budget('商业',depth_for('reference'))==1200
    chapters=[{'idx':i,'title':f'知识章节 {i+1}'} for i in range(200)]
    analyses=[{'concepts':[{'name':f'概念 {i+1}','chapter':ch['title']}]} for i,ch in enumerate(chapters)]
    chapter_map,topic_index,chapter_rows,topic_rows=build_indexes(chapters,analyses,[[] for _ in chapters])
    assert 'ch200' in chapter_map and '概念 200' in topic_index
    files={f'chapters/ch{i+1:03d}.md':'# 章节蒸馏知识' for i in range(200)}
    files.update({'chapter-map.md':chapter_map,'topic-index.md':topic_index,'patterns.md':'# 方法','cheatsheet.md':'# 决策','glossary.md':'# 术语'})
    files['SKILL.md']=build_master({'title':'长书','author':'作者'},'long-book',{'core':'规则：条件触发行动。\n\n'*1000},chapter_rows,topic_rows,files)
    result=validate_package(files)
    assert result['masterTokens']<=4000;assert result['chapterFiles']==200
    merged=merge_analysis(analyses,{})
    assert len(merged['concepts'])==200
    limited=bounded_context(merged,2500)
    assert len(json.dumps(limited,ensure_ascii=False))<=2500
    files['SKILL.md']+='\n[错误](chapters/missing.md)'
    with pytest.raises(ValueError,match='不存在'):validate_package(files)

@pytest.mark.asyncio
async def test_router_uses_topic_index_and_decision_layer(client):
    from backend.agent import routed_knowledge
    bid=client.post('/api/demo').json()['id']
    for path,content in {'topic-index.md':'# 主题索引\n- **复盘** → [ch003](chapters/ch003.md)',
            'chapters/ch003.md':'# 按需蒸馏知识\n复盘的步骤与适用条件。',
            'cheatsheet.md':'# 决策规则\n当预期与实际不同，检查假设。',
            'patterns.md':'# 操作步骤\n记录结果、比较预期、改善行动。'}.items():
        db.execute('INSERT INTO skill_files VALUES(?,?,?,?) ON CONFLICT(bookId,path) DO UPDATE SET content=excluded.content',(db.uid(),bid,path,content))
    retrieval.index_skills(bid)
    values=await routed_knowledge(bid,'如何应用复盘',llm.Config(**CONFIG))
    assert [v['path'] for v in values[:3]]==['cheatsheet.md','patterns.md','chapters/ch003.md']
    assert (await routed_knowledge(bid,'第3章',llm.Config(**CONFIG)))[0]['path']=='chapters/ch003.md'


def test_import_upstream_style_without_original_text(client):
    master='---\nname: example-framework\ndescription: Knowledge base from Example\n---\n\n# 框架样书\n**Author**: Example Author | **Chapters**: 1\n\n## Core Frameworks\n条件触发行动。\n\n[章节](chapters/ch01-example.md)'
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:
        z.writestr('example-framework/SKILL.md',master)
        z.writestr('example-framework/chapters/ch01-example.md','# 章节知识\n当需要判断时，确认适用条件。')
        z.writestr('example-framework/patterns.md','# 方法\n明确条件后行动。')
    r=client.post('/api/skills/import',files={'file':('skill.zip',buffer.getvalue())});assert r.status_code==200,r.text
    book=r.json();assert book['title']=='框架样书';assert book['author']=='Example Author';assert book['metadata']['name']=='example-framework'
    assert book['chapterCount']==0 # distilled prose must not be misrepresented as original evidence
    assert client.get(f'/api/books/{book["id"]}/search',params={'q':'判断','kind':'skill'}).json()
    assert client.get(f'/api/books/{book["id"]}/search',params={'q':'判断','kind':'book'}).json()==[]
    assert client.post(f'/api/books/{book["id"]}/generate',json={'config':CONFIG}).status_code==400


def test_generation_purpose_validation_and_versioned_checkpoint(client):
    from backend.book_to_skill.spec import GENERATOR_VERSION
    bid=upload(client)
    reference=client.get(f'/api/books/{bid}/estimate',params={'purpose':'reference'}).json()
    study=client.get(f'/api/books/{bid}/estimate',params={'purpose':'all'}).json()
    assert study['outputTokens']>reference['outputTokens']
    assert study['generatorVersion']==GENERATOR_VERSION
    assert client.post(f'/api/books/{bid}/generate',json={'config':CONFIG,'purpose':'bad'}).status_code==422
    db.execute('INSERT INTO checkpoints VALUES(?,?,?)',(bid,'old-map',json.dumps({'summary':'old'})))
    assert worker.checkpoint(bid,'old-map') is None
    worker.save_checkpoint(bid,'new-map',{'summary':'new'})
    assert worker.checkpoint(bid,'new-map')['summary']=='new'
    assert worker.estimate(bid)['checkpoints']==1


def test_structured_json_parser_handles_wrappers_without_salvaging_truncation():
    assert llm.parse_json_object('<think>分析 {非 JSON}</think>\n```json\n{"kind":"商业"}\n```')=={'kind':'商业'}
    assert llm.parse_json_object('结果： {"content":"# 标题\\n正文"}\n附加说明 {不用解析}')=={'content':'# 标题\n正文'}
    assert llm.parse_json_object([{'type':'text','text':'{"kind":"科学"}'}])=={'kind':'科学'}
    for raw in ['{"concepts":[{"name":"部分内容"}]', '[{"kind":"商业"}]', '{}', '<think>{"kind":"商业"}']:
        with pytest.raises(ValueError):llm.parse_json_object(raw)


@pytest.mark.asyncio
async def test_json_generation_retries_invalid_output_and_uses_json_mode(monkeypatch):
    import httpx
    real=httpx.AsyncClient;payloads=[]
    def respond(request):
        payload=json.loads(request.content);payloads.append(payload)
        assert payload['response_format']=={'type':'json_object'}
        content='无效格式' if len(payloads)==1 else '{"content":"# 完整知识"}'
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':content}}]})
    monkeypatch.setattr(llm.httpx,'AsyncClient',lambda **kwargs:real(transport=httpx.MockTransport(respond),**kwargs))
    assert await llm.json_chat(llm.Config(**CONFIG),'原始任务')=={'content':'# 完整知识'}
    assert len(payloads)==2;assert payloads[1]['messages'][1]['content']=='原始任务'
    assert '重新生成完整 JSON' in payloads[1]['messages'][0]['content']


@pytest.mark.asyncio
async def test_json_mode_gateway_fallback_and_length_error(monkeypatch):
    import httpx
    real=httpx.AsyncClient;payloads=[]
    def respond(request):
        payload=json.loads(request.content);payloads.append(payload)
        if 'response_format' in payload:
            return httpx.Response(400,json={'error':{'message':'response_format is not supported'}})
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'```json\n{"kind":"技术"}\n```'}}]})
    monkeypatch.setattr(llm.httpx,'AsyncClient',lambda **kwargs:real(transport=httpx.MockTransport(respond),**kwargs))
    assert await llm.json_chat(llm.Config(**CONFIG),'测试')=={'kind':'技术'}
    assert len(payloads)==2;assert 'response_format' not in payloads[1]
    calls=[]
    def truncated(request):
        calls.append(request)
        # Even apparently valid JSON must not be accepted when the provider
        # explicitly says the result was cut off.
        return httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'{"kind":"技术"}'}}]})
    monkeypatch.setattr(llm.httpx,'AsyncClient',lambda **kwargs:real(transport=httpx.MockTransport(truncated),**kwargs))
    with pytest.raises(llm.LLMError,match='Max Tokens') as caught:await llm.json_chat(llm.Config(**CONFIG),'测试')
    assert len(calls)==2;assert CONFIG['apiKey'] not in str(caught.value)
    calls.clear()
    monkeypatch.setattr(llm.httpx,'AsyncClient',lambda **kwargs:real(transport=httpx.MockTransport(lambda request:httpx.Response(401,json={'error':'SECRET_NOT_PERSISTED'})),**kwargs))
    with pytest.raises(llm.LLMError,match='401'):await llm.json_chat(llm.Config(**CONFIG),'测试')


@pytest.mark.asyncio
async def test_worker_honors_output_budget_for_reasoning_models(client,monkeypatch):
    bid=upload(client);budgets=[]
    async def fake(config,prompt,system):
        budgets.append(config.maxTokens)
        return {'kind':'商业'}
    monkeypatch.setattr(llm,'json_chat',fake)
    config=llm.Config(**{**CONFIG,'maxTokens':16384})
    await worker.cached_call(bid,'budget-test',config,'返回书籍类型')
    assert budgets==[16384]
    await worker.cached_call(bid,'budget-test',config,'返回书籍类型')
    assert budgets==[16384]
