// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
use std::path::PathBuf;
use std::process::Command;

#[tauri::command]
async fn run_pipeline(image_path: String) -> Result<String, String> {
    if image_path.trim().is_empty() {
        return Err("Please choose an image path first.".to_string());
    }

    let image_path = image_path.trim().to_string();

    tauri::async_runtime::spawn_blocking(move || {
        let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
            .map_err(|error| format!("Could not locate repo root: {error}"))?;

        println!("---> Repo root resolved to: {}", repo_root.display());

        let python_path = repo_root.join("mwca_env/bin/python");

        println!("---> Python interpreter resolved to: {}", python_path.display());

        let output = Command::new(&python_path)
            .arg("pipeline.py")
            .arg("--image")
            .arg(image_path)
            .current_dir(&repo_root)
            .output()
            .map_err(|error| format!("Failed to start pipeline: {error}"))?;

        if output.status.success() {
            Ok(String::from_utf8_lossy(&output.stdout).to_string())
        } else {
            let stderr = String::from_utf8_lossy(&output.stderr).to_string();
            if stderr.trim().is_empty() {
                Err("Pipeline failed without stderr output.".to_string())
            } else {
                Err(stderr)
            }
        }
    })
    .await
    .map_err(|join_error| format!("Background task failed: {join_error}"))?
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![run_pipeline])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
