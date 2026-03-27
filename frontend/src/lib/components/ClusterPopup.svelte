<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { scoreToColor, scoreToLabel, scoreToPercent } from '$lib/dryness';
  import type { AreaProperties } from '$lib/api/client';

  export let name: string;
  export let areas: (AreaProperties & { _lon?: number; _lat?: number })[];

  const dispatch = createEventDispatcher<{
    close: void;
    areaSelect: { id: number; name: string; lon: number | undefined; lat: number | undefined };
  }>();

  $: dry = areas.filter((a) => a.dryness_score !== null && a.dryness_score >= 0.70).length;
  $: drying = areas.filter((a) => a.dryness_score !== null && a.dryness_score >= 0.30 && a.dryness_score < 0.70).length;
  $: wet = areas.filter((a) => a.dryness_score !== null && a.dryness_score < 0.30).length;
  $: noData = areas.filter((a) => a.dryness_score === null).length;
</script>

<div class="popup">
  <button class="close" on:click={() => dispatch('close')}>✕</button>

  <div class="header">
    <div class="cluster-name">{name}</div>
    <div class="summary-row">
      <span class="count">{areas.length} areas</span>
      {#if dry > 0}<span class="tag dry">{dry} climbable</span>{/if}
      {#if drying > 0}<span class="tag drying">{drying} drying</span>{/if}
      {#if wet > 0}<span class="tag wet">{wet} wet</span>{/if}
      {#if noData > 0}<span class="tag nodata">{noData} no data</span>{/if}
    </div>
  </div>

  <ul class="area-list">
    {#each areas as area}
      <li>
        <button
          class="area-row"
          on:click={() => dispatch('areaSelect', { id: area.id, name: area.name, lon: area._lon, lat: area._lat })}
        >
          <span class="dot" style="background:{scoreToColor(area.dryness_score)}"></span>
          <span class="area-name">{area.name}</span>
          <span class="area-score">
            {scoreToLabel(area.dryness_score)}
            {#if area.dryness_score !== null}
              <span class="pct">({scoreToPercent(area.dryness_score)})</span>
            {/if}
            {#if area.is_estimated && area.dryness_score === null}
              <em class="est">est.</em>
            {/if}
          </span>
        </button>
      </li>
    {/each}
  </ul>

  <div class="footer">Zoom into an area to see individual boulders</div>
</div>

<style>
  .popup {
    min-width: 260px;
    max-width: 320px;
    font-size: 13px;
    position: relative;
  }

  .close {
    position: absolute;
    top: -2px;
    right: -2px;
    background: none;
    border: none;
    color: #888;
    cursor: pointer;
    font-size: 14px;
    line-height: 1;
    padding: 2px 4px;
  }
  .close:hover { color: #333; }

  .header {
    margin-bottom: 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid #e5e7eb;
  }
  .cluster-name {
    font-size: 15px;
    font-weight: 800;
    margin-bottom: 5px;
    color: #111;
    padding-right: 20px;
  }
  .summary-row {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    align-items: center;
  }
  .count {
    font-size: 11px;
    color: #666;
    margin-right: 2px;
  }
  .tag {
    font-size: 10px;
    font-weight: 600;
    border-radius: 10px;
    padding: 1px 7px;
  }
  .tag.dry    { background: #dcfce7; color: #166534; }
  .tag.drying { background: #fef9c3; color: #854d0e; }
  .tag.wet    { background: #fee2e2; color: #991b1b; }
  .tag.nodata { background: #f3f4f6; color: #6b7280; }

  .area-list {
    list-style: none;
    padding: 0;
    margin: 0 0 8px 0;
    max-height: 300px;
    overflow-y: auto;
  }
  .area-list::-webkit-scrollbar { width: 4px; }
  .area-list::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 2px; }

  .area-row {
    display: flex;
    align-items: center;
    gap: 7px;
    width: 100%;
    background: none;
    border: none;
    border-radius: 6px;
    padding: 5px 6px;
    cursor: pointer;
    text-align: left;
    font-size: 12px;
    transition: background 0.1s;
  }
  .area-row:hover { background: #f3f4f6; }

  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .area-name {
    flex: 1;
    font-weight: 600;
    color: #222;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .area-score {
    font-size: 11px;
    color: #555;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .pct {
    color: #888;
  }
  .est {
    font-style: italic;
    color: #aaa;
    font-size: 10px;
  }
  .footer {
    font-size: 10px;
    color: #9ca3af;
    text-align: center;
    padding-top: 4px;
    border-top: 1px solid #f3f4f6;
    font-style: italic;
  }
</style>
