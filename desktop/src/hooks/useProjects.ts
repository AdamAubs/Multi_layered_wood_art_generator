import { useCallback, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { ProjectSummary } from "../types";

export function useProjects() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [isLoadingProjects, setIsLoadingProjects] = useState(false);
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [projectsError, setProjectsError] = useState("");

  const refreshProjects = useCallback(async () => {
    setProjectsError("");
    setIsLoadingProjects(true);
    try {
      const rows = await invoke<ProjectSummary[]>("list_projects");
      setProjects(rows);
    } catch (e) {
      setProjectsError(String(e));
    } finally {
      setIsLoadingProjects(false);
    }
  }, []);

  const createProject = useCallback(
    async (title: string) => {
      const trimmed = title.trim();
      if (!trimmed) {
        throw new Error("Project title is required.");
      }

      setProjectsError("");
      setIsCreatingProject(true);
      try {
        const created = await invoke<ProjectSummary>("create_project", {
          payload: { title: trimmed },
        });
        await refreshProjects();
        return created;
      } finally {
        setIsCreatingProject(false);
      }
    },
    [refreshProjects],
  );

  return useMemo(
    () => ({
      projects,
      isLoadingProjects,
      isCreatingProject,
      projectsError,
      refreshProjects,
      createProject,
    }),
    [
      projects,
      isLoadingProjects,
      isCreatingProject,
      projectsError,
      refreshProjects,
      createProject,
    ],
  );
}
