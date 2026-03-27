<script lang="ts">
</script>

<svelte:head>
  <title>SecBleau — Is Fontainebleau dry?</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
</svelte:head>

<slot />

<style>
  :global(*, *::before, *::after) {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }
  :global(body) {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f0f4f8;
    color: #222;
  }
  :global(html, body) {
    height: 100%;
    overflow: hidden;
  }
</style>
