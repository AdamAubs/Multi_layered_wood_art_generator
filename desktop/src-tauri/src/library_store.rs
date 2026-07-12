use serde::Serialize;
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

const LIBRARY_DIR_NAME: &str = "LazyLayerzzzLibrary";
const VAULT_SCHEMA_VERSION: u64 = 1;

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

    let now_epoch = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);

    let payload = VaultFile {
        schema_version: VAULT_SCHEMA_VERSION,
        library_name: LIBRARY_DIR_NAME.to_string(),
        created_at_epoch: now_epoch,
    };

    let json = serde_json::to_string_pretty(&payload)
        .map_err(|e| format!("Failed to serialize vault.json payload: {e}"))?;

    fs::write(vault_path, format!("{json}\n"))
        .map_err(|e| format!("Failed to write vault.json at {}: {e}", vault_path.display()))?;

    Ok(())
}

pub fn initialize_library() -> Result<LibraryInitSummary, String> {
    let repo_root = resolve_repo_root()?;
    let library_root = resolve_library_root()?;
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

#[tauri::command]
pub fn ensure_library_initialized() -> Result<LibraryInitSummary, String> {
    initialize_library()
}