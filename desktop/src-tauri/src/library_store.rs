use crate::library_types::{CreateProjectRequest, ProjectSummary, SavedRunSummary};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

const LIBRARY_DIR_NAME: &str = "LazyLayerzzzLibrary";
const VAULT_SCHEMA_VERSION: u64 = 1;
const PROJECT_SCHEMA_VERSION: u32 = 1;

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LibraryInitSummary {
    pub repo_root: String,
    pub library_root: String,
    pub vault_path: String,
    pub projects_path: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct VaultFile {
    schema_version: u64,
    library_name: String,
    created_at_epoch: u64,
}

pub fn resolve_repo_root() -> Result<PathBuf, String> {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .map_err(|e| format!("Could not resolve repository root: {e}"))
}

pub fn resolve_library_root() -> Result<PathBuf, String> {
    Ok(resolve_repo_root()?.join(LIBRARY_DIR_NAME))
}

fn now_epoch() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

fn now_created_at_string() -> String {
    // Keep this simple for now: stable string value without adding dependencies.
    // Later milestones can switch to RFC3339 formatting if desired.
    now_epoch().to_string()
}

fn validate_vault_json(vault_path: &Path) -> Result<(), String> {
    if !vault_path.exists() {
        return Err(format!(
            "Vault file does not exist at {}",
            vault_path.display()
        ));
    }

    if !vault_path.is_file() {
        return Err(format!(
            "Vault path is not a file: {}",
            vault_path.display()
        ));
    }

    let raw = fs::read_to_string(vault_path)
        .map_err(|e| format!("Failed to read vault.json at {}: {e}", vault_path.display()))?;

    let value: Value = serde_json::from_str(&raw)
        .map_err(|e| format!("Invalid JSON in vault.json at {}: {e}", vault_path.display()))?;

    let obj = value
        .as_object()
        .ok_or_else(|| format!("vault.json must contain a JSON object: {}", vault_path.display()))?;

    let schema_version = obj
        .get("schemaVersion")
        .and_then(Value::as_u64)
        .ok_or_else(|| {
            format!(
                "vault.json is missing numeric schemaVersion at {}",
                vault_path.display()
            )
        })?;

    if schema_version != VAULT_SCHEMA_VERSION {
        return Err(format!(
            "Unsupported vault schemaVersion {} in {} (expected {})",
            schema_version,
            vault_path.display(),
            VAULT_SCHEMA_VERSION
        ));
    }

    Ok(())
}

fn ensure_vault_json(vault_path: &Path) -> Result<(), String> {
    if vault_path.exists() {
        return validate_vault_json(vault_path);
    }

    let payload = VaultFile {
        schema_version: VAULT_SCHEMA_VERSION,
        library_name: LIBRARY_DIR_NAME.to_string(),
        created_at_epoch: now_epoch(),
    };

    let json = serde_json::to_string_pretty(&payload)
        .map_err(|e| format!("Failed to serialize vault.json payload: {e}"))?;

    fs::write(vault_path, format!("{json}\n"))
        .map_err(|e| format!("Failed to write vault.json at {}: {e}", vault_path.display()))?;

    Ok(())
}

fn initialize_library_in_root(repo_root: &Path) -> Result<LibraryInitSummary, String> {
    let library_root = repo_root.join(LIBRARY_DIR_NAME);
    let projects_path = library_root.join("projects");
    let vault_path = library_root.join("vault.json");

    fs::create_dir_all(&library_root).map_err(|e| {
        format!(
            "Failed to create library root at {}: {e}",
            library_root.display()
        )
    })?;

    fs::create_dir_all(&projects_path).map_err(|e| {
        format!(
            "Failed to create projects directory at {}: {e}",
            projects_path.display()
        )
    })?;

    ensure_vault_json(&vault_path)?;

    Ok(LibraryInitSummary {
        repo_root: repo_root.to_string_lossy().to_string(),
        library_root: library_root.to_string_lossy().to_string(),
        vault_path: vault_path.to_string_lossy().to_string(),
        projects_path: projects_path.to_string_lossy().to_string(),
    })
}

pub fn initialize_library() -> Result<LibraryInitSummary, String> {
    let repo_root = resolve_repo_root()?;
    initialize_library_in_root(&repo_root)
}

pub fn slugify_project_id(title: &str) -> String {
    let mut out = String::new();
    let mut last_dash = false;

    for ch in title.trim().chars() {
        let c = ch.to_ascii_lowercase();
        if c.is_ascii_alphanumeric() {
            out.push(c);
            last_dash = false;
        } else if !last_dash {
            out.push('-');
            last_dash = true;
        }
    }

    let trimmed = out.trim_matches('-').to_string();
    if trimmed.is_empty() {
        "project".to_string()
    } else {
        trimmed
    }
}

fn parse_project_json(project_json_path: &Path) -> Result<ProjectSummary, String> {
    let raw = fs::read_to_string(project_json_path)
        .map_err(|e| format!("Failed to read {}: {e}", project_json_path.display()))?;

    serde_json::from_str::<ProjectSummary>(&raw).map_err(|e| {
        format!(
            "Invalid project.json at {}: {e}",
            project_json_path.display()
        )
    })
}

fn list_projects_in_root(repo_root: &Path) -> Result<Vec<ProjectSummary>, String> {
    let init = initialize_library_in_root(repo_root)?;
    let projects_root = PathBuf::from(init.projects_path);

    let mut projects = Vec::<ProjectSummary>::new();

    let entries = fs::read_dir(&projects_root)
        .map_err(|e| format!("Failed to read projects dir {}: {e}", projects_root.display()))?;

    for entry in entries {
        let entry = entry.map_err(|e| format!("Failed reading projects entry: {e}"))?;
        let project_dir = entry.path();
        if !project_dir.is_dir() {
            continue;
        }

        let project_json = project_dir.join("project.json");
        if !project_json.is_file() {
            eprintln!(
                "Skipping project without project.json: {}",
                project_dir.display()
            );
            continue;
        }

        match parse_project_json(&project_json) {
            Ok(project) => projects.push(project),
            Err(err) => {
                // Skip malformed records without crashing the app.
                eprintln!("{err}");
            }
        }
    }

    projects.sort_by(|a, b| a.title.to_lowercase().cmp(&b.title.to_lowercase()));
    Ok(projects)
}

fn create_project_in_root(
    repo_root: &Path,
    payload: CreateProjectRequest,
) -> Result<ProjectSummary, String> {
    let title = payload.title.trim().to_string();
    if title.is_empty() {
        return Err("Project title is required.".to_string());
    }

    let init = initialize_library_in_root(repo_root)?;
    let projects_root = PathBuf::from(init.projects_path);

    let project_id = slugify_project_id(&title);
    let project_dir = projects_root.join(&project_id);

    if project_dir.exists() {
        return Err(format!(
            "Project already exists for title '{}'. Existing projectId: {}",
            title, project_id
        ));
    }

    fs::create_dir_all(project_dir.join("runs")).map_err(|e| {
        format!(
            "Failed to create project directories at {}: {e}",
            project_dir.display()
        )
    })?;

    let project = ProjectSummary {
        schema_version: PROJECT_SCHEMA_VERSION,
        project_id: project_id.clone(),
        title,
        created_at: now_created_at_string(),
    };

    let project_json = serde_json::to_string_pretty(&project)
        .map_err(|e| format!("Failed to serialize project.json: {e}"))?;

    fs::write(project_dir.join("project.json"), format!("{project_json}\n"))
        .map_err(|e| format!("Failed to write project.json: {e}"))?;

    Ok(project)
}

#[tauri::command]
pub fn ensure_library_initialized() -> Result<LibraryInitSummary, String> {
    initialize_library()
}

#[tauri::command]
pub fn list_projects() -> Result<Vec<ProjectSummary>, String> {
    let repo_root = resolve_repo_root()?;
    list_projects_in_root(&repo_root)
}

#[tauri::command]
pub fn create_project(payload: CreateProjectRequest) -> Result<ProjectSummary, String> {
    let repo_root = resolve_repo_root()?;
    create_project_in_root(&repo_root, payload)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_temp_root(name: &str) -> PathBuf {
        let mut dir = std::env::temp_dir();
        dir.push(format!("mwca_{name}_{}", now_epoch()));
        fs::create_dir_all(&dir).expect("temp root creation failed");
        dir
    }

    #[test]
    fn slug_conversion_normalizes_title() {
        let slug = slugify_project_id("Chicago Skyline 2014–2026");
        assert_eq!(slug, "chicago-skyline-2014-2026");
    }

    #[test]
    fn duplicate_project_id_is_rejected() {
        let root = make_temp_root("duplicate_project");
        let first = create_project_in_root(
            &root,
            CreateProjectRequest {
                title: "Tomorrow Test".to_string(),
            },
        );
        assert!(first.is_ok());

        let second = create_project_in_root(
            &root,
            CreateProjectRequest {
                title: "Tomorrow Test".to_string(),
            },
        );
        assert!(second.is_err());

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn list_projects_skips_invalid_project_files() {
        let root = make_temp_root("invalid_project_file");
        let init = initialize_library_in_root(&root).expect("init should work");
        let projects_root = PathBuf::from(init.projects_path);

        // Valid project
        create_project_in_root(
            &root,
            CreateProjectRequest {
                title: "Chicago Skyline".to_string(),
            },
        )
        .expect("valid project create should work");

        // Invalid project file
        let bad_dir = projects_root.join("bad-project");
        fs::create_dir_all(&bad_dir).expect("bad dir create failed");
        fs::write(bad_dir.join("project.json"), "{ not-json")
            .expect("bad project write failed");

        let listed = list_projects_in_root(&root).expect("list should still work");
        assert_eq!(listed.len(), 1);
        assert_eq!(listed[0].project_id, "chicago-skyline");

        let _ = fs::remove_dir_all(root);
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LibraryRunEntry {
    pub run: SavedRunSummary,
    pub run_dir_abs: String,
    pub final_output_dir_abs: String,
    pub prompt_saved: bool,
    pub input_filename: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LibraryProjectEntry {
    pub project: ProjectSummary,
    pub runs: Vec<LibraryRunEntry>,
}

fn parse_run_json(run_json_path: &Path) -> Result<SavedRunSummary, String> {
    let raw = fs::read_to_string(run_json_path)
        .map_err(|e| format!("Failed to read {}: {e}", run_json_path.display()))?;

    serde_json::from_str::<SavedRunSummary>(&raw)
        .map_err(|e| format!("Invalid run.json at {}: {e}", run_json_path.display()))
}

fn list_runs_for_project(project_dir: &Path) -> Vec<LibraryRunEntry> {
    let runs_root = project_dir.join("runs");
    if !runs_root.is_dir() {
        return Vec::new();
    }

    let mut runs = Vec::<LibraryRunEntry>::new();

    let entries = match fs::read_dir(&runs_root) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("Failed to read runs dir {}: {e}", runs_root.display());
            return runs;
        }
    };

    for entry in entries {
        let entry = match entry {
            Ok(v) => v,
            Err(e) => {
                eprintln!("Failed reading run entry: {e}");
                continue;
            }
        };

        let run_dir = entry.path();
        if !run_dir.is_dir() {
            continue;
        }

        let run_json = run_dir.join("run.json");
        if !run_json.is_file() {
            eprintln!("Skipping run without run.json: {}", run_dir.display());
            continue;
        }

        match parse_run_json(&run_json) {
            Ok(run) => {
                let final_output_dir = run_dir.join(&run.outputs.final_output);
                let final_output_dir_abs = final_output_dir
                    .canonicalize()
                    .unwrap_or(final_output_dir.clone())
                    .to_string_lossy()
                    .to_string();

                let run_dir_abs = run_dir
                    .canonicalize()
                    .unwrap_or(run_dir.clone())
                    .to_string_lossy()
                    .to_string();

                runs.push(LibraryRunEntry {
                    input_filename: run.source.original_filename.clone(),
                    prompt_saved: run.prompt.is_some(),
                    run,
                    run_dir_abs,
                    final_output_dir_abs,
                });
            }
            Err(err) => {
                eprintln!("{err}");
            }
        }
    }

    // Newest first
    runs.sort_by(|a, b| b.run.created_at.cmp(&a.run.created_at));

    runs
}

fn list_library_projects_with_runs_in_root(
    repo_root: &Path,
) -> Result<Vec<LibraryProjectEntry>, String> {
    let projects = list_projects_in_root(repo_root)?;
    let projects_root = initialize_library_in_root(repo_root)?.projects_path;
    let projects_root = PathBuf::from(projects_root);

    let mut out = Vec::<LibraryProjectEntry>::new();

    for project in projects {
        let project_dir = projects_root.join(&project.project_id);
        let runs = list_runs_for_project(&project_dir);

        out.push(LibraryProjectEntry { project, runs });
    }

    Ok(out)
}

#[tauri::command]
pub fn list_library_projects_with_runs() -> Result<Vec<LibraryProjectEntry>, String> {
    let repo_root = resolve_repo_root()?;
    list_library_projects_with_runs_in_root(&repo_root)
}

#[tauri::command]
pub fn open_in_file_browser(path: String) -> Result<(), String> {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return Err("Path is required.".to_string());
    }

    let target = PathBuf::from(trimmed);
    if !target.exists() {
        return Err(format!("Path does not exist: {}", target.display()));
    }

    #[cfg(target_os = "macos")]
    {
        let status = Command::new("open")
            .arg(&target)
            .status()
            .map_err(|e| format!("Failed to open path {}: {e}", target.display()))?;

        if !status.success() {
            return Err(format!("open command failed for {}", target.display()));
        }
    }

    #[cfg(target_os = "windows")]
    {
        let status = Command::new("explorer")
            .arg(&target)
            .status()
            .map_err(|e| format!("Failed to open path {}: {e}", target.display()))?;

        if !status.success() {
            return Err(format!("explorer command failed for {}", target.display()));
        }
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    {
        let status = Command::new("xdg-open")
            .arg(&target)
            .status()
            .map_err(|e| format!("Failed to open path {}: {e}", target.display()))?;

        if !status.success() {
            return Err(format!("xdg-open command failed for {}", target.display()));
        }
    }

    Ok(())
}