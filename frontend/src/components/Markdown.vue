<script setup lang="ts">
import {computed} from 'vue'
import {marked} from 'marked'
import DOMPurify from 'dompurify'
const props=defineProps<{text:string;internalFiles?:boolean}>()
const emit=defineEmits<{navigate:[path:string]}>()
function navigate(event:MouseEvent){const a=(event.target as Element)?.closest('a');const path=a?.getAttribute('href');if(props.internalFiles && path && /^(?:chapters\/[^/]+|[a-z-]+)\.md$/.test(path)){event.preventDefault();emit('navigate',path)}}
const html=computed(()=>DOMPurify.sanitize(marked.parse(props.text.replace(/^---\r?\nname:[\s\S]*?\r?\n---\r?\n/,''),{async:false}) as string,{FORBID_TAGS:['img','iframe','style'],FORBID_ATTR:['style']}))
</script>
<template><div class="markdown" v-html="html" @click="navigate"/></template>
