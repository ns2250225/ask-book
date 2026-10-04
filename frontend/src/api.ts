export interface Config {baseURL:string;apiKey:string;model:string;temperature:number;maxTokens:number;embeddingModel:string}
export interface Book {id:string;title:string;author:string;language:string;fileType:string;fileHash:string;status:string;createdAt:string;progress:number;stage:string;error:string;kind:string;cover:string;questions:Record<string,string[]>;stats:Record<string,number>;chapterCount:number;metadata:Record<string,any>|null}
export interface Chapter {id:string;title:string;idx:number;chars:number;content?:string}
export interface Reference {id:string;bookId:string;bookTitle:string;chapterId:string;chapter:string;paragraph:number;start:number;end:number;text:string;citation:number}
export interface Message {id:string;role:string;content:string;references:Reference[];createdAt?:string}
export interface Conversation {id:string;title:string;updatedAt:string}
export interface Estimate {tokens:number;chapters:number;sections:number;requests:number;checkpoints:number;inputTokens?:number;outputTokens?:number;depth?:string;generatorVersion?:string}
export async function api<T=any>(path:string,options:RequestInit={}):Promise<T>{
 let r:Response
 try {r=await fetch('/api'+path,{...options,headers:options.body instanceof FormData?options.headers:{'Content-Type':'application/json',...options.headers}})}catch{throw new Error('无法连接本地服务，请确认后端已启动')}
 if(!r.ok){let body;try{body=await r.json()}catch{};throw new Error(typeof body?.detail==='string'?body.detail:Array.isArray(body?.detail)?body.detail.map((x:any)=>x.msg).join('；'):'请求失败 ('+r.status+')')}
 return r.json()
}
export function post<T=any>(path:string,body:any={}):Promise<T>{return api<T>(path,{method:'POST',body:JSON.stringify(body)})}
export const statusLabels:Record<string,string>={parsed:'待转换',generating:'Skill 生成中',ready:'可问书',failed:'生成失败',paused:'已暂停'}
export function date(value:string){return new Date(value).toLocaleDateString('zh-CN',{month:'short',day:'numeric'})}
