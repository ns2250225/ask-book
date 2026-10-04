import {createApp} from 'vue'
import {createPinia} from 'pinia'
import {createRouter,createWebHistory} from 'vue-router'
import App from './App.vue'
import Library from './views/Library.vue'
import Upload from './views/Upload.vue'
import Settings from './views/Settings.vue'
import BookView from './views/BookView.vue'
import SkillView from './views/SkillView.vue'
import './style.css'
const router=createRouter({history:createWebHistory(),routes:[{path:'/',component:Library},{path:'/books/new',component:Upload},{path:'/books/:id',component:BookView},{path:'/books/:id/skill',component:SkillView},{path:'/settings',component:Settings},{path:'/:pathMatch(.*)*',redirect:'/'}]})
createApp(App).use(createPinia()).use(router).mount('#app')
