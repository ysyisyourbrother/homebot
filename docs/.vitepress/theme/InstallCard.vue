<script setup lang="ts">
import { ref } from "vue";

const installMethod = ref<"pypi" | "source">("pypi");
const copied = ref(false);

const commands = {
  pypi: "pip install homebot-ai",
  source: `git clone https://github.com/ysyisyourbrother/homebot
cd homebot
pip install -e .`,
};

async function copyCommand() {
  await navigator.clipboard.writeText(commands[installMethod.value]);
  copied.value = true;
  window.setTimeout(() => (copied.value = false), 1600);
}
</script>

<template>
  <section class="install-card" aria-label="Install Homebot">
    <h2>Install</h2>
    <div class="install-card__tabs" role="tablist" aria-label="Installation method">
      <button
        :class="{ active: installMethod === 'pypi' }"
        type="button"
        role="tab"
        :aria-selected="installMethod === 'pypi'"
        @click="installMethod = 'pypi'"
      >
        PyPI
      </button>
      <button
        :class="{ active: installMethod === 'source' }"
        type="button"
        role="tab"
        :aria-selected="installMethod === 'source'"
        @click="installMethod = 'source'"
      >
        Source
      </button>
    </div>
    <div class="install-card__command">
      <code>{{ commands[installMethod] }}</code>
      <button
        type="button"
        class="install-card__copy"
        :aria-label="copied ? 'Copied' : 'Copy command'"
        :title="copied ? 'Copied' : 'Copy command'"
        @click="copyCommand"
      >
        <svg v-if="!copied" viewBox="0 0 24 24" aria-hidden="true">
          <path
            fill="currentColor"
            d="M8 7V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2Zm2 0h4a2 2 0 0 1 2 2v4h2V5h-8v2Zm4 2H6v10h8V9Z"
          />
        </svg>
        <svg v-else viewBox="0 0 24 24" aria-hidden="true">
          <path fill="currentColor" d="m9 16.17-3.88-3.88L3.7 13.7 9 19l12-12-1.41-1.41L9 16.17Z" />
        </svg>
      </button>
    </div>
  </section>
</template>
