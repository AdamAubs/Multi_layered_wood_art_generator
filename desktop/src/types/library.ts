export type TemplateFamily =
  | "radial-mandala"
  | "skyline-architecture"
  | "flag-emblem"
  | "wreath"
  | "dense-field"
  | "custom";

export type TemplateDoc = {
  filename: string;
  name: string;
  family: TemplateFamily;
  subject: string;
  colorCount: number;
  colorList: string;
  structuralElement: string;
  backgroundColor: string;
  extraNotes: string;
  systemPromptSuffix: string;
  body: string;
  updatedAtEpoch: number;
};

export type TemplateDraft = Omit<TemplateDoc, "filename" | "updatedAtEpoch">;

export type FeedbackSentiment = "good" | "bad";

export type FeedbackPayload = {
  jobId: string;
  finalDir: string | null;
  templateFilename: string | null;
  sentiment: FeedbackSentiment;
  rating: number;
  note: string;
};
