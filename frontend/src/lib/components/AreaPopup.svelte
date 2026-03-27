<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import {
    scoreToColor,
    scoreToLabel,
    scoreToPercent,
    formatHoursSinceRain,
  } from '$lib/dryness';
  import ReportButton from './ReportButton.svelte';

  export let props: Record<string, unknown>;

  const dispatch = createEventDispatcher<{ close: void; reported: { condition: string } }>();

  $: score = (props.dryness_score ?? null) as number | null;
  $: color = scoreToColor(score);
  $: label = scoreToLabel(score);
  $: pct = scoreToPercent(score);
  $: hoursSince = (props.hours_since_rain ?? null) as number | null;
  $: isClimbable = score !== null && score >= 0.70;
  $: badgeTextColor = score !== null && score >= 0.55 ? '#000' : '#fff';
  $: temperatureC = props.temperature_c != null ? Number(props.temperature_c) : null;
  $: humidityPct = props.humidity_pct != null ? Number(props.humidity_pct) : null;
  $: windSpeedMs = props.wind_speed_ms != null ? Number(props.wind_speed_ms) : null;
</script>

<div class="popup">
  <button class="close" on:click={() => dispatch('close')}>✕</button>

  <div class="header" style="border-left: 4px solid {color}">
    <div class="name">{props.name}</div>
    <div class="badge" style="background:{color}; color: {badgeTextColor}">
      {label} — {pct}
    </div>
  </div>

  <div class="stats">
    <div class="stat">
      <span class="stat-label">Rain</span>
      <span class="stat-value">{formatHoursSinceRain(hoursSince)}</span>
    </div>
    {#if temperatureC != null}
      <div class="stat">
        <span class="stat-label">Temp</span>
        <span class="stat-value">{temperatureC.toFixed(1)}°C</span>
      </div>
    {/if}
    {#if humidityPct != null}
      <div class="stat">
        <span class="stat-label">Humidity</span>
        <span class="stat-value">{Math.round(humidityPct)}%</span>
      </div>
    {/if}
    {#if windSpeedMs != null}
      <div class="stat">
        <span class="stat-label">Wind</span>
        <span class="stat-value">{windSpeedMs.toFixed(1)} m/s</span>
      </div>
    {/if}
    <div class="stat">
      <span class="stat-label">Boulders</span>
      <span class="stat-value">{props.boulder_count}</span>
    </div>
  </div>

  {#if props.is_estimated}
    <div class="estimated-note">Physics estimate — zoom in for boulder detail</div>
  {/if}

  <ReportButton mode="area" entityId={Number(props.id)} entityName={String(props.name)} on:reported={(e) => dispatch('reported', e.detail)} />
</div>

<style>
  .popup {
    min-width: 220px;
    max-width: 280px;
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
  .header {
    padding: 8px 10px;
    margin-bottom: 10px;
    border-radius: 4px;
    background: #f9fafb;
  }
  .name {
    font-weight: 700;
    font-size: 14px;
    margin-bottom: 4px;
  }
  .badge {
    display: inline-block;
    border-radius: 12px;
    padding: 2px 10px;
    font-weight: 600;
    font-size: 12px;
  }
  .stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px 10px;
    margin-bottom: 8px;
  }
  .stat { display: flex; flex-direction: column; }
  .stat-label { font-size: 10px; color: #888; text-transform: uppercase; letter-spacing: 0.04em; }
  .stat-value { font-size: 13px; font-weight: 600; color: #222; }
  .estimated-note {
    font-size: 11px;
    color: #666;
    font-style: italic;
    margin-bottom: 4px;
  }
</style>
