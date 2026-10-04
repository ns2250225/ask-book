import {defineStore} from 'pinia'
import {ref} from 'vue'
import {api,type Book,type Config} from './api'
const defaults:Config={baseURL:'https://api.openai.com/v1',apiKey:'',model:'',temperature:.3,maxTokens:8192,embeddingModel:''}
async function configDB(){return new Promise<IDBDatabase>((resolve,reject)=>{const r=indexedDB.open('bookskill-private',1);r.onupgradeneeded=()=>r.result.createObjectStore('settings');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(new Error('浏览器禁止 IndexedDB，请允许本地存储'))})}
export const useStore=defineStore('main',()=>{
 const books=ref<Book[]>([]),loading=ref(false),error=ref(''),toast=ref(''),config=ref<Config>({...defaults}),configLoaded=ref(false)
 let timer:ReturnType<typeof setTimeout>|undefined
 function notify(message:string){toast.value=message;clearTimeout(timer);timer=setTimeout(()=>toast.value='',4200)}
 async function loadBooks(){loading.value=true;error.value='';try{books.value=await api<Book[]>('/books')}catch(e){error.value=(e as Error).message}finally{loading.value=false}}
 async function loadConfig(){try{const db=await configDB();const value=await new Promise<any>((resolve,reject)=>{const r=db.transaction('settings').objectStore('settings').get('llm');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)});config.value={...defaults,...value};db.close()}catch(e){notify((e as Error).message)}finally{configLoaded.value=true}}
 async function saveConfig(value:Config){const db=await configDB();await new Promise<void>((resolve,reject)=>{const t=db.transaction('settings','readwrite');t.objectStore('settings').put({...value},'llm');t.oncomplete=()=>resolve();t.onerror=()=>reject(t.error)});db.close();config.value={...value}}
 return {books,loading,error,toast,config,configLoaded,notify,loadBooks,loadConfig,saveConfig}
})
