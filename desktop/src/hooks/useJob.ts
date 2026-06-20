import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { JobSnapshot } from "../types";
import { isTerminal } from "../utils/statusHelpers";
import { POLLING_INTERVAL } from "../utils/constants";

export function useJob() {
  const [job, setJob] = useState<JobSnapshot | null>(null);
  const [uiError, setUiError] = useState("");
  const pollRef = useRef<number | null>(null);

  async function fetchStatus() {
    const latest = await invoke<JobSnapshot>("get_job_status");
    setJob(latest);

    if (isTerminal(latest.status) && pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function startJob(
    imagePath: string,
    stockSizeIn: string | null = null,
    bridgeCountIn: number | null = null,
    mergeVisibleFractionIn: number | null = null,
  ) {
    setUiError("");

    const trimmed = imagePath.trim();
    if (!trimmed) {
      setUiError("Please enter an image path first.");
      return;
    }

    try {
      const started = await invoke<JobSnapshot>("start_job", {
        imagePath: trimmed,
        stockSizeIn: stockSizeIn ?? null,
        bridgeCountIn: bridgeCountIn ?? null,
        mergeVisibleFraction: mergeVisibleFractionIn ?? null,
      });
      setJob(started);

      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
      }

      pollRef.current = window.setInterval(() => {
        fetchStatus().catch((e) => {
          setUiError(String(e));
        });
      }, POLLING_INTERVAL);
    } catch (e) {
      setUiError(String(e));
    }
  }

  useEffect(() => {
    fetchStatus().catch((e) => setUiError(String(e)));
    return () => {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
      }
    };
  }, []);

  return { job, uiError, startJob };
}
