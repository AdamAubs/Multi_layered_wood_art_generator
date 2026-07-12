export type JobStatus =
  | "idle"
  | "preprocessing"
  | "generating"
  | "postprocessing"
  | "complete"
  | "failed";

export type JobSnapshot = {
  job_id: string;
  status: JobStatus;
  elapsed_sec: number;
  message: string;
  error: string | null;
  n_colors: number | null;
  palette: { id: number; rgb: [number, number, number] }[];
  current_layer: number | null;
  winner_history: { layer: number; color_id: number; patches: number }[];
  final_dir: string | null;
};

export type FinalArtifact = {
  name: string;
  abs_path: string;
  ext: string;
  previewable: boolean;
  category: string;
};

export * from "./libraryContracts";
