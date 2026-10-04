<script setup lang="ts">
import {computed} from 'vue'
import {BookOpen} from 'lucide-vue-next'
const props=defineProps<{book:{title:string;author:string;cover?:string;id?:string};small?:boolean}>()
const color=computed(()=>['sage','ochre','slate','brick','indigo'][(props.book.id||props.book.title).split('').reduce((a,c)=>a+c.charCodeAt(0),0)%5])
</script>
<template><div class="book-cover" :class="[color,{small}]" :aria-label="book.title+'封面'"><img v-if="book.cover" :src="book.cover" alt="书籍封面"/><template v-else><div class="cover-top">BOOK / KNOWLEDGE</div><div class="cover-title">{{book.title.replace(' · 功能示例','')}}</div><div class="cover-line"></div><div class="cover-author">{{book.author}}</div><BookOpen class="cover-symbol" :size="small?20:32" :stroke-width="1"/><div class="cover-bottom">问书 · BOOKSKILL</div></template></div></template>
