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
