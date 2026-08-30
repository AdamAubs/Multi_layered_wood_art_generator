import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { FrameShape, JobSnapshot } from "../types";
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
    projectId: string,
    imagePath: string,
    prompt: string | null,
    stockSizeIn: string | null = null,
    bridgeCountIn: number | null = null,
    mergeVisibleFractionIn: number | null = null,
    omegaBudgetFactorIn: number | null = null,
    fabSizeIn: string | null = null,
    frameShape: FrameShape = "rectangle",
    dxfFrameMarginMm: number | null = null,
    dxfSettingHoleDiameterMm: number | null = null,
    dxfSettingHoleInsetMm: number | null = null,
    addFrenchCleats = false,
    createEtsyRelease = false,
  ) {
    setUiError("");

    const projectIdTrimmed = projectId.trim();
    if (!projectIdTrimmed) {
      setUiError("Please select a project first.");
      return;
    }

    const imagePathTrimmed = imagePath.trim();
    if (!imagePathTrimmed) {
      setUiError("Please enter an image path first.");
      return;
    }

    const normalizedPrompt = prompt?.trim() ?? "";
    const promptOrNull = normalizedPrompt.length > 0 ? normalizedPrompt : null;

    try {
      const started = await invoke<JobSnapshot>("start_job", {
        projectId: projectIdTrimmed,
        imagePath: imagePathTrimmed,
        prompt: promptOrNull,
        stockSizeIn: stockSizeIn ?? null,
        bridgeCountIn: bridgeCountIn ?? null,
        mergeVisibleFraction: mergeVisibleFractionIn ?? null,
        omegaBudgetFactor: omegaBudgetFactorIn ?? null,
        fabSizeIn: fabSizeIn ?? null,
        frameShape,
        dxfFrameMarginMm: dxfFrameMarginMm ?? null,
        dxfSettingHoleDiameterMm: dxfSettingHoleDiameterMm ?? null,
        dxfSettingHoleInsetMm: dxfSettingHoleInsetMm ?? null,
        addFrenchCleats,
        createEtsyRelease,
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
