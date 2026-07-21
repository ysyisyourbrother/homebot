<script setup lang="ts">
import { useRoute } from "vitepress";
import DefaultTheme from "vitepress/theme";
import InstallCard from "./InstallCard.vue";

const { Layout } = DefaultTheme;
const route = useRoute();
</script>

<template>
  <Layout>
    <template #home-hero-image>
      <InstallCard />
    </template>
    <template #layout-bottom>
      <footer v-if="route.data.relativePath === 'index.md'" class="site-footer">
        <div class="site-footer__inner">
          <span>MIT License</span>
          <div class="site-footer__right">
            <span>Contact</span>
            <a
              href="https://github.com/ysyisyourbrother/homebot"
              aria-label="GitHub"
              target="_blank"
              rel="noreferrer"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path
                  fill="currentColor"
                  d="M12 2a10 10 0 0 0-3.16 19.49c.5.09.68-.22.68-.48v-1.7c-2.78.6-3.37-1.18-3.37-1.18-.46-1.16-1.11-1.47-1.11-1.47-.9-.62.07-.61.07-.61 1 .07 1.52 1.02 1.52 1.02.89 1.52 2.33 1.08 2.9.82.09-.64.35-1.08.63-1.33-2.22-.25-4.56-1.11-4.56-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.65 0 0 .84-.27 2.75 1.02A9.54 9.54 0 0 1 12 6.8c.85 0 1.71.11 2.51.34 1.91-1.29 2.75-1.02 2.75-1.02.55 1.38.2 2.4.1 2.65.64.7 1.03 1.59 1.03 2.68 0 3.84-2.35 4.69-4.58 4.94.36.31.68.9.68 1.81v2.68c0 .26.18.57.69.48A10 10 0 0 0 12 2Z"
                />
              </svg>
            </a>
            <a href="mailto:brandonye@foxmail.com" aria-label="Email">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path
                  fill="currentColor"
                  d="M3 5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h18a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H3Zm0 2h18v.51l-9 5.63-9-5.63V7Zm0 10V9.86l8.47 5.3a1 1 0 0 0 1.06 0L21 9.86V17H3Z"
                />
              </svg>
            </a>
          </div>
        </div>
      </footer>
    </template>
  </Layout>
</template>
