import { useCallback, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { TemplateDoc, TemplateDraft } from "../types/library";

const emptyDraft: TemplateDraft = {
  name: "",
  family: "radial-mandala",
  subject: "",
  colorCount: 4,
  colorList: "",
  structuralElement: "bands",
  backgroundColor: "solid white",
  extraNotes: "",
  systemPromptSuffix: "",
  body: "",
};

export function useTemplates() {
  const [templates, setTemplates] = useState<TemplateDoc[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    setIsLoading(true);
    try {
      const rows = await invoke<TemplateDoc[]>("list_templates");
      setTemplates(rows);
    } catch (e) {
      setError(String(e));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const save = useCallback(
    async (draft: TemplateDraft, existingFilename?: string) => {
      setError("");
      const saved = await invoke<TemplateDoc>("save_template", {
        payload: {
          existingFilename: existingFilename ?? null,
          template: draft,
        },
      });
      await refresh();
      return saved;
    },
    [refresh],
  );

  const remove = useCallback(
    async (filename: string) => {
      setError("");
      await invoke("delete_template", { filename });
      await refresh();
    },
    [refresh],
  );

  return useMemo(
    () => ({
      templates,
      isLoading,
      error,
      refresh,
      save,
      remove,
      emptyDraft,
    }),
    [templates, isLoading, error, refresh, save, remove],
  );
}
