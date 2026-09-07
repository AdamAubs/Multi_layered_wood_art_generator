use std::fs;
use std::path::PathBuf;
use crate::types::FinalArtifact;

pub fn artifact_category(ext: &str) -> (&'static str, bool) {
    match ext {
        "png" => ("image", true),
        "dxf" => ("vector", false),
        "md" => ("doc", false),
        "json" => ("data", false),
        "txt" => ("text", false),
        _ => ("other", false),
    }
}

#[tauri::command]
pub fn list_final_artifacts(final_dir: String) -> Result<Vec<FinalArtifact>, String> {
    let dir = PathBuf::from(final_dir.trim());

    if !dir.exists() {
        return Err(format!("Final directory does not exist: {}", dir.display()));
    }
    if !dir.is_dir() {
        return Err(format!("Path is not a directory: {}", dir.display()));
    }

    let mut out: Vec<FinalArtifact> = Vec::new();

    let entries = fs::read_dir(&dir)
        .map_err(|e| format!("Failed to read final directory: {e}"))?;

    for entry in entries {
        let entry = entry.map_err(|e| format!("Bad directory entry: {e}"))?;
        let path = entry.path();
        if !path.is_file() {
            continue;
        }

        let ext = path
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_ascii_lowercase();

        if !matches!(ext.as_str(), "png" | "dxf" | "md" | "json" | "txt") {
            continue;
        }

        let (category, previewable) = artifact_category(&ext);

        let name = path
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_string();

        let abs_path = path
            .canonicalize()
            .unwrap_or(path.clone())
            .to_string_lossy()
            .to_string();

        out.push(FinalArtifact {
            name,
            abs_path,
            ext,
            previewable,
            category: category.to_string(),
        });
    }

    out.sort_by(|a, b| {
        let a_png_layer = a.ext == "png" && a.name.starts_with("Layer_");
        let b_png_layer = b.ext == "png" && b.name.starts_with("Layer_");

        match (a_png_layer, b_png_layer) {
            (true, false) => std::cmp::Ordering::Less,
            (false, true) => std::cmp::Ordering::Greater,
            _ => a.name.to_lowercase().cmp(&b.name.to_lowercase()),
        }
    });

    Ok(out)
}
#[tauri::command]
pub fn read_finished_dimensions(final_dir: String) -> Result<Option<serde_json::Value>, String> {
    let path = PathBuf::from(final_dir).join("dimensions.json");
    if !path.exists() { return Ok(None); }
    let text = fs::read_to_string(path).map_err(|e| format!("Cannot read dimensions: {e}"))?;
    let value = serde_json::from_str(&text).map_err(|e| format!("Invalid dimensions: {e}"))?;
    Ok(Some(value))
}
