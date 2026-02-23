<template>
  <Transition name="fade-down">
    <div class="error-banner" role="alert">
      <span class="error-banner-indicator"></span>
      <p class="error-banner-message">
        {{ message }}
      </p>
    </div>
  </Transition>
</template>

<script setup lang="ts">
defineProps<{
  message: string;
}>();
</script>

