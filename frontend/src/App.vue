<script setup lang="ts">
import {onMounted,computed} from 'vue'
import {useRoute} from 'vue-router'
import {BookOpen,Library,Plus,Settings,ArrowUpRight,ShieldCheck,PanelLeftClose} from 'lucide-vue-next'
import {useStore} from './store'
const store=useStore(),route=useRoute()
const bookPage=computed(()=>/^\/books\/(?!new)[^/]+/.test(route.path))
onMounted(()=>{store.loadConfig();store.loadBooks()})
</script>
<template>
 <div class="app-shell" :class="{'reading-shell':bookPage}">
  <aside class="main-sidebar">
   <RouterLink to="/" class="brand" aria-label="问书 · 我的书架"><span class="brand-icon"><BookOpen :size="23" :stroke-width="1.6"/></span><span>问书<small>BOOKSKILL</small></span></RouterLink>
   <div class="sidebar-caption">我的阅读空间</div>
   <nav><RouterLink to="/" class="nav-item" active-class="active" :exact-active-class="'active'"><Library :size="19"/>我的书架<span class="nav-count">{{store.books.length}}</span></RouterLink><RouterLink to="/books/new" class="nav-item"><Plus :size="19"/>添加书籍</RouterLink></nav>
   <div class="sidebar-recent" v-if="store.books.length"><div class="sidebar-caption">最近添加</div><RouterLink v-for="b in store.books.slice(0,4)" :key="b.id" :to="'/books/'+b.id" class="recent-item"><span class="mini-spine"></span><span>{{b.title}}</span></RouterLink></div>
   <div class="sidebar-bottom"><div class="local-card"><ShieldCheck :size="19"/><div>知识属于你<small>本地存储 · 随时导出</small></div></div><RouterLink to="/settings" class="nav-item"><Settings :size="18"/>AI 模型设置<span class="connection-dot" :class="{on:store.config.model}"/></RouterLink><div class="version">BOOKSKILL <span>V1.0</span></div></div>
  </aside>
  <main class="workspace"><header class="topbar"><div class="breadcrumb"><span>阅读空间</span><span class="slash">/</span><strong>{{route.path==='/settings'?'AI 模型设置':route.path==='/books/new'?'添加书籍':bookPage?'书籍工作台':'我的书架'}}</strong></div><div class="topbar-right"><span class="local-pill"><span></span>本地工作空间</span><a href="/api/docs" target="_blank" rel="noopener" class="text-link">API 文档<ArrowUpRight :size="14"/></a></div></header><RouterView/></main>
 </div><Transition name="toast"><div v-if="store.toast" class="toast-message" role="status"><ShieldCheck :size="17"/>{{store.toast}}</div></Transition>
</template>
