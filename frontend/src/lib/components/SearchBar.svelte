<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { api, type BoulderSearchResult } from '$lib/api/client';
  import { scoreToColor } from '$lib/dryness';

  const dispatch = createEventDispatcher<{
    select: BoulderSearchResult;
  }>();

  let query = '';
  let results: BoulderSearchResult[] = [];
  let loading = false;
  let open = false;
  let activeIndex = -1;
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;

  function onInput() {
    activeIndex = -1;
    if (debounceTimer) clearTimeout(debounceTimer);
    const q = query.trim();
    if (q.length < 2) {
      results = [];
      open = false;
      return;
    }
    debounceTimer = setTimeout(async () => {
      loading = true;
      try {
        results = await api.searchBoulders(q);
        open = results.length > 0;
      } catch {
        results = [];
        open = false;
      } finally {
        loading = false;
      }
    }, 300);
  }

  function select(r: BoulderSearchResult) {
    query = '';
    results = [];
    open = false;
    activeIndex = -1;
    dispatch('select', r);
  }

  function onKeydown(e: KeyboardEvent) {
    if (!open) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = Math.min(activeIndex + 1, results.length - 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
    } else if (e.key === 'Enter' && activeIndex >= 0) {
      e.preventDefault();
      select(results[activeIndex]);
    } else if (e.key === 'Escape') {
      open = false;
    }
  }

  function onBlur() {
    // Delay so a mouse click on a result fires before the list closes
    setTimeout(() => { open = false; activeIndex = -1; }, 150);
  }
</script>

<div class="search-wrap">
  <div class="input-row">
    <span class="icon">🔍</span>
    <input
      type="text"
      class="input"
      placeholder="Search boulder problems…"
      bind:value={query}
      on:input={onInput}
      on:keydown={onKeydown}
      on:blur={onBlur}
      autocomplete="off"
      spellcheck="false"
      aria-label="Search boulder problems"
      aria-expanded={open}
      aria-haspopup="listbox"
      role="combobox"
    />
    {#if loading}
      <span class="spinner"></span>
    {:else if query.length > 0}
      <button class="clear" on:click={() => { query = ''; results = []; open = false; }} aria-label="Clear search">✕</button>
    {/if}
  </div>

  {#if open}
    <ul class="results" role="listbox">
      {#each results as r, i}
        <li
          class="result"
          class:active={i === activeIndex}
          role="option"
          aria-selected={i === activeIndex}
          on:mousedown|preventDefault={() => select(r)}
        >
          <span class="dot" style="background:{scoreToColor(null)}"></span>
          <span class="result-name">
            {r.name ?? 'Unnamed'}
            {#if r.grade}<span class="grade">{r.grade}</span>{/if}
          </span>
          <span class="result-area">{r.area_name ?? '—'}</span>
        </li>
      {/each}
      {#if results.length === 0 && !loading}
        <li class="no-results">No boulders found</li>
      {/if}
    </ul>
  {/if}
</div>

<style>
  .search-wrap {
    position: relative;
    flex: 1;
    max-width: 320px;
    min-width: 160px;
  }

  .input-row {
    display: flex;
    align-items: center;
    background: rgba(255,255,255,0.1);
    border: 1px solid rgba(255,255,255,0.18);
    border-radius: 8px;
    padding: 0 8px;
    gap: 6px;
    height: 32px;
    transition: background 0.15s, border-color 0.15s;
  }
  .input-row:focus-within {
    background: rgba(255,255,255,0.18);
    border-color: rgba(255,255,255,0.4);
  }

  .icon { font-size: 13px; flex-shrink: 0; opacity: 0.7; }

  .input {
    flex: 1;
    background: none;
    border: none;
    outline: none;
    color: #fff;
    font-size: 13px;
    min-width: 0;
  }
  .input::placeholder { color: #9ca3af; }

  .clear {
    background: none;
    border: none;
    color: #9ca3af;
    cursor: pointer;
    font-size: 12px;
    padding: 0 2px;
    line-height: 1;
    flex-shrink: 0;
  }
  .clear:hover { color: #fff; }

  .spinner {
    width: 12px;
    height: 12px;
    border: 2px solid rgba(255,255,255,0.2);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
    flex-shrink: 0;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .results {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    right: 0;
    background: #1f2937;
    border: 1px solid #374151;
    border-radius: 8px;
    list-style: none;
    margin: 0;
    padding: 4px 0;
    z-index: 50;
    max-height: 280px;
    overflow-y: auto;
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  }

  .result {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    cursor: pointer;
    transition: background 0.1s;
  }
  .result:hover, .result.active { background: #374151; }

  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
    background: #6b7280;
  }

  .result-name {
    flex: 1;
    font-size: 13px;
    color: #f9fafb;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .grade {
    background: #374151;
    border-radius: 4px;
    padding: 1px 5px;
    font-size: 10px;
    font-weight: 700;
    color: #d1d5db;
    flex-shrink: 0;
  }

  .result-area {
    font-size: 11px;
    color: #6b7280;
    flex-shrink: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 120px;
  }

  .no-results {
    padding: 10px 12px;
    font-size: 12px;
    color: #6b7280;
    text-align: center;
  }
</style>
