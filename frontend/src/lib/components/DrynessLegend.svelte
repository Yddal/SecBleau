<script lang="ts">
  const stops = [
    { color: '#d73027', label: 'Wet' },
    { color: '#f46d43', label: 'Damp' },
    { color: '#fdae61', label: 'Drying' },
    { color: '#a6d96a', label: '≥70% Climbable' },
    { color: '#1a9641', label: 'Excellent' },
  ];

  const opacityLevels = [
    { opacity: 1.0, label: 'Direct reports (last 48h)' },
    { opacity: 0.60, label: 'Area reports (estimated)' },
    { opacity: 0.35, label: 'No reports (physics only)' },
  ];
</script>

<div class="legend">
  <div class="section">
    <div class="section-title">Dryness</div>
    {#each stops as stop}
      <div class="row">
        <span class="swatch" style="background:{stop.color}"></span>
        <span class="label">{stop.label}</span>
      </div>
    {/each}
  </div>

  <div class="section">
    <div class="section-title">Confidence</div>
    {#each opacityLevels as level}
      <div class="row">
        <span class="swatch opacity-swatch" style="opacity:{level.opacity}"></span>
        <span class="label">{level.label}</span>
      </div>
    {/each}
  </div>
</div>

<style>
  .legend {
    background: rgba(255, 255, 255, 0.94);
    border-radius: 8px;
    padding: 10px 14px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.18);
    font-size: 12px;
    min-width: 180px;
  }
  .section {
    margin-bottom: 10px;
  }
  .section:last-child {
    margin-bottom: 0;
  }
  .section-title {
    font-weight: 700;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #555;
    margin-bottom: 5px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 7px;
    margin-bottom: 3px;
  }
  .swatch {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #1a9641;
    flex-shrink: 0;
    border: 1.5px solid rgba(0,0,0,0.12);
  }
  .opacity-swatch {
    background: #888888;
  }
  .label {
    color: #333;
    line-height: 1.3;
  }
</style>
