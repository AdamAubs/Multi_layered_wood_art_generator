mod types;
mod state;
mod log_parser;
mod log_tail;
mod artifacts;
mod pipeline;

pub use types::{JobStatus, JobSnapshot, PaletteColor, LayerWinner, FinalArtifact, JobState};
pub use artifacts::list_final_artifacts;
pub use pipeline::{start_job, get_job_status};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            start_job,
            get_job_status,
            list_final_artifacts
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}