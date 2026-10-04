import asyncio, json, re
import httpx
from pydantic import BaseModel, Field, field_validator

class Config(BaseModel):
    baseURL:str='https://api.openai.com/v1'
    apiKey:str=''
    model:str=Field(min_length=1,max_length=200)
    temperature:float=Field(default=.3,ge=0,le=2)
    maxTokens:int=Field(default=8192,ge=256,le=65536)
    embeddingModel:str=''
    @field_validator('baseURL')
    @classmethod
    def valid_url(cls,v):
        from urllib.parse import urlparse
        u=urlparse(v)
        if u.scheme not in ('https','http') or not u.hostname or u.username or u.password or u.query or u.fragment:
            raise ValueError('API URL 必须是有效的 HTTP(S) 地址')
        return v.rstrip('/')

class LLMError(Exception): pass

async def chat(config, messages, tools=None, max_tokens=None, json_mode=False):
    body={'model':config.model,'messages':messages,'temperature':config.temperature,'max_tokens':max_tokens or config.maxTokens}
    if json_mode: body['response_format']={'type':'json_object'}
    if tools: body['tools']=tools; body['tool_choice']='auto'
    async with httpx.AsyncClient(timeout=httpx.Timeout(180,connect=15)) as client:
        for attempt in range(3):
            try:
                response=await client.post(config.baseURL+'/chat/completions',headers={'Authorization':'Bearer '+config.apiKey},json=body)
                if response.status_code in (429,502,503,504) and attempt<2:
                    await asyncio.sleep(2**attempt); continue
                if response.status_code>=400:
                    # Some compatible gateways have no JSON mode. Retry the same
                    # request without it only when that parameter is rejected.
                    if response.status_code in (400,422) and 'response_format' in body:
                        try: error=response.json().get('error',{})
                        except ValueError: error={}
                        detail=str(error) if isinstance(error,(dict,str)) else ''
                        if 'response_format' in detail.lower() and attempt<2:
                            body.pop('response_format'); continue
                    # Never echo provider bodies: they can include credentials or prompt content.
                    detail={401:'API Key 无效，请检查 AI 设置',403:'API 权限不足',404:'请检查 API URL 和 Model',429:'请求过于频繁，请稍后继续',400:'请求参数或上下文长度不被模型接受',413:'上下文过长'}.get(response.status_code,'AI 服务返回错误')
                    raise LLMError(f'{response.status_code} · {detail}')
                value=response.json()
                message=value['choices'][0]['message']
                if json_mode:
                    message['_finish_reason']=value['choices'][0].get('finish_reason')
                if not message.get('content') and not message.get('tool_calls') and not (json_mode and message['_finish_reason']=='length'):
                    raise LLMError('AI 返回了空内容，请换用支持文本输出的模型')
                return message
            except (httpx.TimeoutException,httpx.NetworkError):
                if attempt==2: raise LLMError('AI 服务连接超时或不可达，请检查 URL、网络及服务状态')
            except (KeyError,ValueError): raise LLMError('AI 返回格式不兼容，需要 OpenAI chat/completions 接口')

def parse_json_object(content):
    if isinstance(content,list):
        content='\n'.join(x.get('text','') for x in content if isinstance(x,dict) and isinstance(x.get('text'),str))
    if not isinstance(content,str): raise ValueError('missing text')
    # Reasoning text can contain braces; never interpret it as result data.
    raw=re.sub(r'<think>.*?</think>','',content,flags=re.S|re.I).strip()
    if raw.lower().startswith('<think>'): raise ValueError('unfinished reasoning')
    fenced=re.findall(r'```(?:json)?\s*\n(.*?)```',raw,flags=re.S|re.I)
    for candidate in [*fenced,raw]:
        candidate=candidate.strip()
        if candidate.startswith('['): continue
        start=candidate.find('{')
        if start<0: continue
        try:
            value,_=json.JSONDecoder().raw_decode(candidate[start:])
            if isinstance(value,dict) and value:return value
        except ValueError: pass
    raise ValueError('invalid JSON object')

async def json_chat(config, prompt, system='请只返回合法 JSON，不要使用 Markdown 代码块。'):
    truncated=False
    for attempt in range(2):
        instruction='' if not attempt else '\n上次输出未满足完整 JSON 要求。请重新生成完整 JSON 对象：精简文字，只保留原文支持的重点；Markdown 正文放在 JSON 字符串内并正确转义换行和引号。不要输出思考过程、说明或代码块，必须在输出预算内闭合全部字符串、数组和对象。'
        m=await chat(config,[{'role':'system','content':system+instruction},{'role':'user','content':prompt}],json_mode=True)
        truncated=m.get('_finish_reason')=='length'
        if truncated: continue
        try:return parse_json_object(m.get('content'))
        except ValueError:pass
    if truncated:
        raise LLMError('模型输出达到 Max Tokens 上限，结构化内容未完成。请在 AI 设置提高 Max Tokens（推理模型需预留思考预算），然后继续生成；已完成内容会复用')
    raise LLMError('模型连续两次未返回完整 JSON，已自动重试。请检查模型是否支持 JSON 输出，然后继续生成；已完成内容会复用')

async def embeddings(config,texts):
    async with httpx.AsyncClient(timeout=60) as client:
        r=await client.post(config.baseURL+'/embeddings',headers={'Authorization':'Bearer '+config.apiKey},json={'model':config.embeddingModel,'input':texts})
        if r.status_code>=400: raise LLMError('Embedding 接口不可用，请检查模型设置或关闭混合检索')
        try: return [x['embedding'] for x in sorted(r.json()['data'],key=lambda x:x['index'])]
        except (KeyError,TypeError): raise LLMError('Embedding 返回格式不兼容')
