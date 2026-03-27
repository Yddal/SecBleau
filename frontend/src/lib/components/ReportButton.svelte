<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import {
    BOULDER_CONDITIONS,
    AREA_CONDITIONS,
    SANDSTONE_SAFETY_NOTE,
    scoreToColor,
  } from '$lib/dryness';
  import { api } from '$lib/api/client';

  export let mode: 'boulder' | 'area' = 'boulder';
  export let entityId: number;
  export let entityName: string = '';

  const dispatch = createEventDispatcher<{ reported: { condition: string } }>();

  let showForm = false;
  let showSafety = false;
  let selected: string | null = null;
  let submitting = false;
  let error: string | null = null;
  let success = false;

  $: conditions = mode === 'boulder' ? BOULDER_CONDITIONS : AREA_CONDITIONS;

  async function submit() {
    if (!selected) return;
    submitting = true;
    error = null;
    try {
      if (mode === 'boulder') {
        await api.reportBoulder(entityId, selected);
      } else {
        await api.reportArea(entityId, selected);
      }
      success = true;
      dispatch('reported', { condition: selected });
      setTimeout(() => {
        showForm = false;
        success = false;
        selected = null;
      }, 4000);
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : 'Something went wrong. Please try again.';
    } finally {
      submitting = false;
    }
  }
</script>

{#if !showForm}
  <button class="report-btn" on:click={() => showForm = true}>
    📍 Report conditions
  </button>
{:else}
  <div class="form">
    {#if success}
      <div class="success">✓ Report submitted — thanks!</div>
    {:else}
      <div class="form-title">
        {mode === 'boulder' ? 'Boulder' : 'Area'} condition
        {#if entityName}<span class="entity-name">— {entityName}</span>{/if}
      </div>

      <!-- Safety note toggle -->
      <button class="safety-toggle" on:click={() => showSafety = !showSafety}>
        ⚠️ Why sandstone dryness matters
      </button>

      {#if showSafety}
        <div class="safety-note">{SANDSTONE_SAFETY_NOTE}</div>
      {/if}

      <!-- Condition options -->
      <div class="options">
        {#each conditions as cond}
          <button
            class="option"
            class:selected={selected === cond.value}
            style="--color:{cond.color}"
            on:click={() => selected = cond.value}
          >
            <span class="dot" style="background:{cond.color}"></span>
            <span>
              <strong>{cond.label}</strong>
              <span class="desc">{cond.description}</span>
            </span>
          </button>
        {/each}
      </div>

      {#if error}
        <div class="error">{error}</div>
      {/if}

      <div class="actions">
        <button class="cancel" on:click={() => { showForm = false; selected = null; error = null; }}>
          Cancel
        </button>
        <button class="submit" disabled={!selected || submitting} on:click={submit}>
          {submitting ? 'Submitting…' : 'Submit'}
        </button>
      </div>

      <div class="privacy-note">
        No personal data is stored. Your report is anonymised.
        <a href="/privacy" target="_blank" rel="noopener">Privacy notice</a>
      </div>
    {/if}
  </div>
{/if}

<style>
  .report-btn {
    background: #2563eb;
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: 7px 14px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    width: 100%;
    margin-top: 8px;
  }
  .report-btn:hover { background: #1d4ed8; }

  .form {
    margin-top: 8px;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 12px;
  }
  .form-title {
    font-weight: 700;
    font-size: 13px;
    margin-bottom: 8px;
  }
  .entity-name { font-weight: 400; color: #666; }

  .safety-toggle {
    background: none;
    border: none;
    color: #b45309;
    font-size: 11px;
    cursor: pointer;
    padding: 0;
    text-decoration: underline;
    margin-bottom: 6px;
  }
  .safety-note {
    font-size: 11px;
    color: #78350f;
    background: #fef3c7;
    border: 1px solid #fbbf24;
    border-radius: 6px;
    padding: 8px;
    margin-bottom: 8px;
    white-space: pre-line;
    line-height: 1.5;
  }

  .options {
    display: flex;
    flex-direction: column;
    gap: 5px;
    margin-bottom: 8px;
  }
  .option {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    background: #fff;
    border: 2px solid #e5e7eb;
    border-radius: 7px;
    padding: 8px;
    cursor: pointer;
    text-align: left;
    font-size: 12px;
    transition: border-color 0.15s;
  }
  .option.selected {
    border-color: var(--color);
    background: color-mix(in srgb, var(--color) 10%, white);
  }
  .dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
    margin-top: 2px;
  }
  .desc {
    color: #666;
    display: block;
    font-size: 11px;
    margin-top: 1px;
  }

  .error {
    color: #dc2626;
    font-size: 12px;
    margin-bottom: 6px;
  }
  .success {
    color: #16a34a;
    font-weight: 600;
    font-size: 13px;
    text-align: center;
    padding: 8px;
  }

  .actions {
    display: flex;
    gap: 6px;
    justify-content: flex-end;
  }
  .cancel {
    background: none;
    border: 1px solid #d1d5db;
    color: #374151;
    border-radius: 5px;
    padding: 5px 12px;
    cursor: pointer;
    font-size: 12px;
  }
  .submit {
    background: #16a34a;
    color: #fff;
    border: none;
    border-radius: 5px;
    padding: 5px 14px;
    cursor: pointer;
    font-size: 12px;
    font-weight: 600;
  }
  .submit:disabled { opacity: 0.5; cursor: not-allowed; }

  .privacy-note {
    font-size: 10px;
    color: #9ca3af;
    text-align: center;
    margin-top: 8px;
  }
  .privacy-note a { color: #9ca3af; text-decoration: underline; }
  .privacy-note a:hover { color: #374151; }
</style>
