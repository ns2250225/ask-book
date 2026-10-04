import re, hashlib, io, zipfile
from pathlib import Path
from bs4 import BeautifulSoup
from charset_normalizer import from_bytes
from ebooklib import epub, ITEM_DOCUMENT
import pymupdf as fitz

MAX_BYTES=50*1024*1024

def split_chapters(text, fallback='正文'):
    text=text.replace('\r\n','\n').replace('\x00','')
    lines=text.splitlines(); chunks=[]; title=fallback; buf=[]
    heading=re.compile(r'^\s*(?:#{1,6}\s+.+|第[零一二三四五六七八九十百千\d]+[章节部卷篇].{0,60}|(?:chapter|part)\s+[\divxlc]+.{0,60})\s*$',re.I)
    for line in lines:
        if heading.match(line):
            if ''.join(buf).strip(): chunks.append({'title':title,'content':'\n'.join(buf).strip()})
            title=re.sub(r'^#+\s*','',line.strip()); buf=[]
        else: buf.append(line)
    if ''.join(buf).strip(): chunks.append({'title':title,'content':'\n'.join(buf).strip()})
    return chunks

def parse(path:Path, original_name:str):
    ext=path.suffix.lower(); title=Path(original_name).stem; author='未知作者'; cover=''; pages=0
    if ext=='.epub':
        with zipfile.ZipFile(path) as z:
            if sum(x.file_size for x in z.infolist())>200*1024*1024: raise ValueError('EPUB 解压内容超过 200 MB 限制')
        b=epub.read_epub(str(path),options={'ignore_ncx':True})
        names=b.get_metadata('DC','title'); authors=b.get_metadata('DC','creator')
        if names: title=names[0][0]
        if authors: author=authors[0][0]
        chapters=[]
        for item_id,_ in b.spine:
            item=b.get_item_with_id(item_id)
            if item and item.get_type()==ITEM_DOCUMENT:
                soup=BeautifulSoup(item.get_content(),'html.parser')
                for tag in soup(['script','style','nav']): tag.decompose()
                header=soup.find(['h1','h2','h3']); content=soup.get_text('\n',strip=True)
                if len(content)>30: chapters.append({'title':header.get_text(' ',strip=True) if header else f'章节 {len(chapters)+1}','content':content})
        for item in b.get_items():
            if 'cover-image' in getattr(item,'properties',[]) and item.media_type in ('image/jpeg','image/png','image/webp'):
                import base64
                raw=item.get_content()
                if len(raw)<3*1024*1024: cover=f'data:{item.media_type};base64,'+base64.b64encode(raw).decode()
                break
    elif ext=='.pdf':
        doc=fitz.open(path)
        if doc.needs_pass: raise ValueError('PDF 已加密，请上传未加密的文件')
        pages=len(doc); page_lines=[]; repeated={}
        for page in doc:
            # Sort independently inside each column when text blocks reveal a wide gutter.
            blocks=[x for x in page.get_text('blocks') if len(x)>6 and x[6]==0]
            mid=page.rect.width/2
            left=[x for x in blocks if x[2]<mid+10]; right=[x for x in blocks if x[0]>mid-10]
            if len(left)>2 and len(right)>2:
                spanning=[x for x in blocks if x not in left and x not in right]
                blocks=sorted(spanning,key=lambda x:x[1])+sorted(left,key=lambda x:x[1])+sorted(right,key=lambda x:x[1])
            else: blocks=sorted(blocks,key=lambda x:(round(x[1]/8),x[0]))
            lines='\n'.join(x[4] for x in blocks).splitlines(); page_lines.append(lines)
            for s in set(lines[:2]+lines[-2:]):
                s=s.strip()
                if s: repeated[s]=repeated.get(s,0)+1
        doc.close()
        remove={s for s,n in repeated.items() if pages>3 and n>=max(3,pages*.5)}
        cleaned=[]
        for lines in page_lines:
            kept=[s for i,s in enumerate(lines) if not ((i<2 or i>=len(lines)-2) and (s.strip() in remove or re.fullmatch(r'\s*[-–]?\s*\d+\s*[-–]?\s*',s)))]
            cleaned.append('\n'.join(kept))
        text='\n\n'.join(cleaned)
        if len(re.sub(r'\s','',text))<max(80,pages*25): raise ValueError('当前 PDF 未检测到足够的可复制文本，暂不支持纯扫描版 PDF。')
        text=re.sub(r'(?<=[A-Za-z])-\n(?=[a-z])','',text)
        text=re.sub(r'(?<=[\u4e00-\u9fff，、])\n(?=[\u4e00-\u9fff])','',text)
        chapters=split_chapters(text)
    elif ext in ('.txt','.md','.markdown'):
        raw=path.read_bytes(); match=from_bytes(raw).best()
        if match is None: raise ValueError('无法识别文本编码，请转换为 UTF-8 后重试')
        text=str(match)
        if ext in ('.md','.markdown'):
            first=re.search(r'^#\s+(.+)',text,re.M)
            if first: title=first.group(1)
        chapters=split_chapters(text)
    else: raise ValueError('支持 EPUB / PDF / TXT / Markdown')
    if not chapters: raise ValueError('未提取到有效正文，请检查电子书文件')
    if sum(len(x['content']) for x in chapters)>5_000_000: raise ValueError('正文超过 500 万字符限制，请拆分书籍')
    return {'title':title,'author':author,'language':'zh' if re.search('[\u4e00-\u9fff]',chapters[0]['content']) else 'en','chapters':chapters,'cover':cover,'pages':pages}

def content_hash(text): return hashlib.sha256(text.encode()).hexdigest()

def sections(text, limit=10000):
    # Every character is retained; oversized paragraphs are split before chapter synthesis.
    out=[]; buf=''
    for p in text.splitlines(keepends=True):
        while len(p)>limit:
            if buf: out.append(buf); buf=''
            out.append(p[:limit]); p=p[limit:]
        if len(buf)+len(p)>limit:
            out.append(buf); buf=''
        buf+=p
    if buf.strip(): out.append(buf)
    return out or [text]


def estimate_tokens(text):
    import math
    chinese=len(re.findall(r"[\u4e00-\u9fff]",text))
    return math.ceil(chinese*1.5+(len(text)-chinese)/4)
