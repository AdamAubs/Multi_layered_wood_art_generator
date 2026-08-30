export type RunStatus = "pending" | "running" | "completed" | "failed";
export type FrameShape = "rectangle" | "first_layer";

export type ProjectSummary = {
  schemaVersion: number;
  projectId: string;
  title: string;
  createdAt: string;
};

export type CreateProjectRequest = {
  title: string;
};

export type ParameterSnapshot = {
  stockSizeIn: string | null;
  supportBridgesPerPatch: number;
  mergeVisibleFraction: number | null;
  omegaBudgetFactor: number | null;
  fabSizeIn?: string | null;
  frameShape?: FrameShape;
  dxfFrameMarginMm?: number | null;
  dxfSettingHoleDiameterMm?: number | null;
  dxfSettingHoleInsetMm?: number | null;
  addFrenchCleats?: boolean;
  createEtsyRelease?: boolean;
  generateCompositePreview: boolean;
  generateShowcasePreview: boolean;
};

export type CreateRunRequest = {
  projectId: string;
  inputImagePath: string;
  prompt: string | null;
  parameters: ParameterSnapshot;
};

export type RunSource = {
  originalFilename: string;
  inputPath: string;
};

export type PromptRef = {
  path: string;
};

export type OutputPaths = {
  generator: string;
  postprocessed: string;
  finalOutput: string;
};

export type SavedRunSummary = {
  schemaVersion: number;
  runId: string;
  projectId: string;
  status: RunStatus;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  source: RunSource;
  prompt: PromptRef | null;
  parameters: ParameterSnapshot;
  outputs: OutputPaths;
  runtimeLogPath: string;
  exitCode: number | null;
};

export type LibraryRunEntry = {
  run: SavedRunSummary;
  runDirAbs: string;
  finalOutputDirAbs: string;
  promptSaved: boolean;
  inputFilename: string;
};

export type LibraryProjectEntry = {
  project: ProjectSummary;
  runs: LibraryRunEntry[];
};
