/**
 * Stage bar model: a version's painting passes, sized by work done.
 *
 * Built from reveal.json keyframes (label + op count) when available, else
 * from the stage labels alone (equal widths). Long stages are split by the
 * server into consecutive keyframes with the same label; they merge into one
 * segment here.
 */

import type { RevealManifest } from '../types';

export interface StageSpec {
  label: string;
  /** Reveal ops in this keyframe; null when unknown (labels only). */
  ops: number | null;
}

export type StageState = 'done' | 'current' | 'pending';

export interface StageSegment {
  key: string;
  label: string;
  ops: number | null;
  /** Share of the bar, 0..1; all segments sum to 1. */
  weight: number;
  state: StageState;
}

/** Every segment gets at least this share of the bar so short passes stay visible. */
export const STAGE_MIN_SHARE = 0.06;

export function stagesFromManifest(manifest: RevealManifest): StageSpec[] {
  return manifest.keyframes.map((kf) => ({ label: kf.label, ops: kf.ops.length }));
}

export function stagesFromLabels(labels: readonly string[]): StageSpec[] {
  return labels.map((label) => ({ label, ops: null }));
}

interface StageGroup {
  label: string;
  ops: number | null;
  first: number;
  last: number;
}

function groupStages(stages: readonly StageSpec[]): StageGroup[] {
  const groups: StageGroup[] = [];
  stages.forEach((stage, i) => {
    const prev = groups[groups.length - 1];
    if (prev && prev.label === stage.label) {
      prev.last = i;
      prev.ops = prev.ops === null || stage.ops === null ? null : prev.ops + stage.ops;
      return;
    }
    groups.push({ label: stage.label, ops: stage.ops, first: i, last: i });
  });
  return groups;
}

function stateFor(group: StageGroup, activeKeyframe: number | null): StageState {
  if (activeKeyframe === null || group.last < activeKeyframe) return 'done';
  if (group.first <= activeKeyframe) return 'current';
  return 'pending';
}

/**
 * @param activeKeyframe keyframe being revealed (earlier ones are done, later
 *   ones pending), or null when the whole version is shown.
 */
export function buildStageBar(
  stages: readonly StageSpec[],
  activeKeyframe: number | null,
  minShare: number = STAGE_MIN_SHARE
): StageSegment[] {
  const groups = groupStages(stages);
  if (groups.length === 0) return [];

  const known = groups.every((g) => g.ops !== null);
  const total = known ? groups.reduce((sum, g) => sum + (g.ops ?? 0), 0) : 0;
  const raw = groups.map((g) =>
    known && total > 0 ? Math.max((g.ops ?? 0) / total, minShare) : 1
  );
  const rawTotal = raw.reduce((a, b) => a + b, 0);

  return groups.map((g, i) => ({
    key: `${g.first}-${g.label}`,
    label: g.label,
    ops: g.ops,
    weight: raw[i]! / rawTotal,
    state: stateFor(g, activeKeyframe),
  }));
}

/** A segment shows its own label only when it is at least this wide (px). */
export const STAGE_LABEL_MIN_PX = 72;

/**
 * True when every segment is wide enough for its full label.
 * @param barWidth bar width in px; @param gap px between segments;
 * @param measure label text width in px.
 */
export function stageLabelsFit(
  segments: readonly StageSegment[],
  barWidth: number,
  gap: number,
  measure: (label: string) => number,
  minPx: number = STAGE_LABEL_MIN_PX
): boolean {
  if (segments.length === 0 || barWidth <= 0) return false;
  const usable = barWidth - gap * (segments.length - 1);
  return segments.every((s) => {
    const width = s.weight * usable;
    return width >= minPx && width >= measure(s.label || '—');
  });
}

/**
 * One caption for the whole bar when per-segment labels don't fit:
 * "stage 4 of 8 · harbor" while revealing, "8 stages · final touches" when done.
 */
export function stageBarCaption(segments: readonly StageSegment[]): string {
  const n = segments.length;
  if (n === 0) return '';
  const current = segments.findIndex((s) => s.state === 'current');
  if (current >= 0) {
    return `stage ${current + 1} of ${n} · ${segments[current]!.label || '—'}`;
  }
  const last = segments[n - 1]!;
  return `${n} stage${n === 1 ? '' : 's'} · ${last.label || '—'}`;
}
