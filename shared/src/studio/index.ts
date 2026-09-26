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
  parseToolSeconds,
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
export {
  STAGE_LABEL_MIN_PX,
  STAGE_MIN_SHARE,
  buildStageBar,
  stageBarCaption,
  stageLabelsFit,
  stagesFromLabels,
  stagesFromManifest,
} from './stageBar';

export type { MarkdownBlock, MarkdownSpan, NotebookViewItem } from './notebookView';
export {
  DOMAIN_TOOLS,
  buildNotebookView,
  critiqueLabel,
  housekeepingLabel,
  isHousekeepingTool,
  markdownToPlainText,
  parseInlineMarkdown,
  parseMarkdownBlocks,
  toolLabel,
} from './notebookView';

export type { TitleSource } from './titles';
export { PROMPT_TITLE_MAX, pieceDisplayTitle, truncateText } from './titles';

export type { StudioPhase } from './phase';
export { deriveStudioPhase, isActivePhase } from './phase';
