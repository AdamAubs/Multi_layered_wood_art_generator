import { JobStatus } from "../types";

export function isRunningStatus(status: JobStatus) {
  return (
    status === "preprocessing" ||
    status === "generating" ||
    status === "postprocessing"
  );
}

export function isTerminal(status: JobStatus) {
  return status === "complete" || status === "failed";
}
