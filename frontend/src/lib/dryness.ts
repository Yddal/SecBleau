/**
 * Dryness score utilities — colour, labels, opacity.
 * Fixed thresholds matching the backend model.
 */

export const CLIMBABLE_THRESHOLD = 0.70;

export function scoreToColor(score: number | null): string {
  if (score === null) return '#aaaaaa';
  if (score < 0.30) return '#d73027';   // red — wet
  if (score < 0.55) return '#f46d43';   // orange-red — damp
  if (score < 0.70) return '#fdae61';   // orange — approaching threshold
  if (score < 0.85) return '#a6d96a';   // yellow-green — climbable
  return '#1a9641';                      // green — excellent
}

export function scoreToLabel(score: number | null): string {
  if (score === null) return 'No data';
  if (score < 0.30) return 'Wet';
  if (score < 0.55) return 'Damp';
  if (score < 0.70) return 'Drying';
  if (score < 0.85) return 'Climbable';
  return 'Excellent';
}

export function scoreToPercent(score: number | null): string {
  if (score === null) return '—';
  return `${Math.round(score * 100)}%`;
}

/**
 * Opacity based on data confidence level.
 * - Full opacity: has direct boulder reports in last 48h
 * - 60%: area reports exist but no direct boulder reports
 * - 35%: pure physics estimate, no reports at all
 */
export function boulderOpacity(
  hasRecentBoulderReports: boolean,
  isEstimated: boolean
): number {
  if (hasRecentBoulderReports) return 1.0;
  if (!isEstimated) return 0.60;  // physics model + area reports
  return 0.35;                    // pure estimate
}

export function formatHoursSinceRain(hours: number | null): string {
  if (hours === null) return 'No recent rain recorded';
  if (hours < 1) return 'Rain less than 1 hour ago';
  if (hours < 24) return `Rain ${Math.round(hours)}h ago`;
  const days = Math.floor(hours / 24);
  const remaining = Math.round(hours % 24);
  if (remaining === 0) return `Rain ${days}d ago`;
  return `Rain ${days}d ${remaining}h ago`;
}

// Condition labels shown in the report UI
export const BOULDER_CONDITIONS = [
  {
    value: 'wet',
    label: 'Wet',
    description: 'Rock is visibly or tactilely wet — do not climb',
    color: '#d73027',
  },
  {
    value: 'drying',
    label: 'Drying',
    description: 'Improving but not ready — cool or slightly damp to the touch',
    color: '#fdae61',
  },
  {
    value: 'climbable',
    label: 'Climbable',
    description: 'Rock is dry and safe to climb',
    color: '#1a9641',
  },
] as const;

export const AREA_CONDITIONS = [
  {
    value: 'wet',
    label: 'Wet',
    description: 'Area generally unclimbable — rock is wet',
    color: '#d73027',
  },
  {
    value: 'drying',
    label: 'Drying',
    description: 'Rain has stopped, drying in progress',
    color: '#fdae61',
  },
  {
    value: 'some_boulders_dry',
    label: 'Some boulders dry',
    description: 'Mixed conditions — sheltered or south-facing boulders may be climbable',
    color: '#a6d96a',
  },
  {
    value: 'dry',
    label: 'Dry',
    description: 'Area is generally in good condition',
    color: '#1a9641',
  },
] as const;

// Safety information shown to users before they report
export const SANDSTONE_SAFETY_NOTE = `Fontainebleau sandstone is fragile when wet.
Climbing on damp rock permanently damages holds and the rock surface for everyone.

A boulder is climbable only when:
• The surface feels completely dry to the touch — no cool or damp sensation
• Chalk from previous sessions is not darkened or wet-looking
• At least 24–48 hours of dry weather have passed after significant rain
  (shaded or north-facing boulders need longer)
• The ground around the base is not waterlogged`;
