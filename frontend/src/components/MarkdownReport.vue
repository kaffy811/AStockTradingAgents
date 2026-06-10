<template>
  <div class="report-markdown" v-html="rendered"></div>
</template>

<script setup>
import { computed } from 'vue'
import { renderMarkdown } from '../utils/markdown.js'

const props = defineProps({
  content: { type: String, default: '' },
})

const rendered = computed(() => renderMarkdown(props.content))
</script>

<!--
  No scoped styles here. All .report-markdown rules are in src/styles/markdown.css
  because v-html injected content does not receive Vue scoped data-v-* attributes.
-->
