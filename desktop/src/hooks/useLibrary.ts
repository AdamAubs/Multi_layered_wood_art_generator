import { useCallback, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { LibraryProjectEntry } from "../types";

export function useLibrary() {
  const [projects, setProjects] = useState<LibraryProjectEntry[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    setIsLoading(true);
    try {
      const rows = await invoke<LibraryProjectEntry[]>(
        "list_library_projects_with_runs",
      );
      setProjects(rows);
    } catch (e) {
      setProjects([]);
      setError(String(e));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const openPath = useCallback(async (path: string) => {
    await invoke("open_in_file_browser", { path });
  }, []);

  return useMemo(
    () => ({
      projects,
      isLoading,
      error,
      refresh,
      openPath,
    }),
    [projects, isLoading, error, refresh, openPath],
  );
}
