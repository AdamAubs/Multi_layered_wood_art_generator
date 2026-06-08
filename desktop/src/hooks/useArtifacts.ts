import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { FinalArtifact, JobSnapshot } from "../types";

export function useArtifacts(job: JobSnapshot | null) {
  const [artifacts, setArtifacts] = useState<FinalArtifact[]>([]);
  const [artifactsError, setArtifactsError] = useState("");
  const [isLoadingArtifacts, setIsLoadingArtifacts] = useState(false);

  async function fetchFinalArtifacts(finalDir: string) {
    setArtifactsError("");
    setIsLoadingArtifacts(true);

    try {
      const files = await invoke<FinalArtifact[]>("list_final_artifacts", {
        finalDir,
      });
      setArtifacts(files);
    } catch (e) {
      setArtifacts([]);
      setArtifactsError(String(e));
    } finally {
      setIsLoadingArtifacts(false);
    }
  }

  useEffect(() => {
    if (job?.status === "complete" && job.final_dir) {
      fetchFinalArtifacts(job.final_dir);
    }

    if (job?.status !== "complete") {
      setArtifacts([]);
      setArtifactsError("");
    }
  }, [job?.status, job?.final_dir]);

  return { artifacts, artifactsError, isLoadingArtifacts };
}
