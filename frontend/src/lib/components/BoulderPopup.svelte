<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import {
    scoreToColor,
    scoreToLabel,
    scoreToPercent,
    formatHoursSinceRain,
    boulderOpacity,
    CLIMBABLE_THRESHOLD,
  } from '$lib/dryness';
  import ReportButton from './ReportButton.svelte';

  export let props: Record<string, unknown>;

  const dispatch = createEventDispatcher<{ close: void }>();

  $: score = (props.dryness_score ?? null) as number | null;
  $: color = scoreToColor(score);
  $: label = scoreToLabel(score);
  $: pct = scoreToPercent(score);
  $: hoursSince = (props.hours_since_rain ?? null) as number | null;
  $: isEstimated = Boolean(props.is_estimated);
  $: hasRecentReports = Boolean(props.has_recent_reports);
  $: opacity = boulderOpacity(hasRecentReports, isEstimated);
  $: isClimbable = score !== null && score >= CLIMBABLE_THRESHOLD;
  $: badgeTextColor = score !== null && score >= 0.55 ? '#000' : '#fff';
  $: confidenceLevel = opacity === 1.0 ? 'High (direct reports)' : opacity >= 0.6 ? 'Medium (area data)' : 'Low (physics estimate)';
</script>

<div class="popup">
  <button class="close" on:click={() => dispatch('close')}>✕</button>

  <div class="header" style="border-left: 4px solid {color}">
    <div class="name">
      {props.name || 'Unnamed boulder'}
      {#if props.grade}<span class="grade">{props.grade}</span>{/if}
    </div>
    <div class="badge" style="background:{color}; color: {badgeTextColor}">
      {label} — {pct}
    </div>
  </div>

  <div class="stats">
    <div class="stat">
      <span class="stat-label">Last rain</span>
      <span class="stat-value">{formatHoursSinceRain(hoursSince)}</span>
    </div>
    <div class="stat">
      <span class="stat-label">Confidence</span>
      <span class="stat-value">{confidenceLevel}</span>
    </div>
    <div class="stat">
      <span class="stat-label">Reports</span>
      <span class="stat-value">{props.report_count || 0} total</span>
    </div>
    <div class="stat">
      <span class="stat-label">Area</span>
      <span class="stat-value">{props.area_name || '—'}</span>
    </div>
  </div>

  {#if isEstimated && !hasRecentReports}
    <div class="confidence-bar low">
      ⚠️ Estimated from area weather — be the first to report this boulder!
    </div>
  {:else if !hasRecentReports}
    <div class="confidence-bar medium">
      Based on physics model + area reports. Zoom for more detail.
    </div>
  {:else}
    <div class="confidence-bar high">
      ✓ Based on direct condition reports
    </div>
  {/if}

  <ReportButton
    mode="boulder"
    entityId={Number(props.id)}
    entityName={String(props.name || 'this boulder')}
    on:reported
  />
</div>

<style>
  .popup {
    min-width: 220px;
    max-width: 270px;
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
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  .grade {
    background: #e5e7eb;
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 11px;
    font-weight: 700;
    color: #374151;
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
  .stat-value { font-size: 12px; font-weight: 600; color: #222; }

  .confidence-bar {
    font-size: 11px;
    border-radius: 5px;
    padding: 5px 8px;
    margin-bottom: 6px;
    line-height: 1.4;
  }
  .confidence-bar.low { background: #fef3c7; color: #92400e; border: 1px solid #fbbf24; }
  .confidence-bar.medium { background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; }
  .confidence-bar.high { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
</style>
