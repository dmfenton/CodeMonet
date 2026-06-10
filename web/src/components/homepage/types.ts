/**
 * Shared types for Homepage components
 */

export interface StrokePoint {
  x: number;
  y: number;
}

export type PathDataType = 'line' | 'quadratic' | 'cubic' | 'polyline' | 'svg';

export interface PathData {
  type: PathDataType;
  points?: StrokePoint[];
  d?: string;
  author?: string;
  color?: string;
  stroke_width?: number;
  opacity?: number;
  fill?: string;
  fill_opacity?: number;
}

export interface GalleryPiece {
  id: string;
  user_id: string;
  piece_number: number;
  stroke_count: number;
  width?: number;
  height?: number;
  created_at: string;
  title?: string; // Piece title (set by agent via name_piece tool)
}

export interface PieceStrokes {
  id: string;
  strokes: PathData[];
  piece_number: number;
  canvas_width?: number;
  canvas_height?: number;
  created_at: string;
}

export interface SimulatedStroke {
  id: number;
  points: StrokePoint[];
  color: string;
  width: number;
  progress: number;
}

// dmfenton.net-inspired palette: forest ink, cream paper, brass, moss.
export const PALETTE = {
  paper: ['#fdfbf5', '#fffdf8', '#f6efd6'],
  forest: ['#1f4d34', '#102e1e', '#3a7a55'],
  moss: ['#5a9a70', '#6a8a78', '#90b0a0'],
  brass: ['#e8c98a', '#d8b66c', '#caa55c'],
  clay: ['#9b4f45', '#7a5746', '#1a1d18'],
  ink: ['#1a1d18', '#2f3f32', '#6a7468'],
};

// Flattened array of all colors for random selection
export const ALL_COLORS = [
  ...PALETTE.forest,
  ...PALETTE.moss,
  ...PALETTE.brass,
  ...PALETTE.clay,
  ...PALETTE.ink,
];

// Subset of prominent colors for simulated strokes
export const STROKE_COLORS = [
  '#1f4d34', // forest
  '#102e1e', // deep forest
  '#3a7a55', // green
  '#5a9a70', // moss
  '#6a8a78', // grey green
  '#e8c98a', // brass
  '#9b4f45', // clay red
  '#1a1d18', // ink
];
