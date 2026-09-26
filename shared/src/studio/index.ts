/**
 * Studio view models: notebook, version history, stage bar, titles, phase.
 */

export type { NotebookEntry, NotebookVersions } from './notebook';
export {
  MAX_NOTEBOOK_ENTRIES,
  addNote,
  addNudge,
  appendThought,
  attachProducedVersion,
  parseCritique,
  recordToolMessage,
  sealThought,
  toolDetail,
} from './notebook';

export type { VersionHistory } from './versions';
export {
  EMPTY_VERSION_HISTORY,
  latestVersionNumber,
  seedVersionHistory,
  summaryFromRef,
  upsertVersion,
} from './versions';

export type { StageSegment, StageSpec, StageState } from './stageBar';
export { STAGE_MIN_SHARE, buildStageBar, stagesFromLabels, stagesFromManifest } from './stageBar';

export type { TitleSource } from './titles';
export { PROMPT_TITLE_MAX, pieceDisplayTitle, truncateText } from './titles';

export type { StudioPhase } from './phase';
export { STUDIO_PHASE_LABELS, deriveStudioPhase, isActivePhase } from './phase';
