mod types;
mod state;
mod log_parser;
mod log_tail;
mod artifacts;
mod pipeline;
mod template_store;
mod library_types;
mod library_store;

pub use types::{JobStatus, JobSnapshot, PaletteColor, LayerWinner, FinalArtifact, JobState};
pub use artifacts::list_final_artifacts;
pub use pipeline::{start_job, get_job_status};
pub use template_store::{list_templates, save_template, delete_template};
pub use library_store::{ensure_library_initialized, list_projects, create_project, list_library_projects_with_runs, open_in_file_browser};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    if let Err(e) = library_store::initialize_library() {
        eprintln!("Library initialization warning: {e}");
    }

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            start_job,
            get_job_status,
            list_final_artifacts,
            list_templates,
            save_template,
            delete_template,
            ensure_library_initialized,
            list_projects,
            create_project,
            list_library_projects_with_runs,
            open_in_file_browser,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}