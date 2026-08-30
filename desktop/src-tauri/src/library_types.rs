use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "snake_case")]
pub enum FrameShape {
    #[default]
    Rectangle,
    FirstLayer,
}

impl FrameShape {
    pub fn as_cli_value(self) -> &'static str {
        match self {
            Self::Rectangle => "rectangle",
            Self::FirstLayer => "first_layer",
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum RunStatus {
    Pending,
    Running,
    Completed,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectSummary {
    pub schema_version: u32,
    pub project_id: String,
    pub title: String,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CreateProjectRequest {
    pub title: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ParameterSnapshot {
    pub stock_size_in: Option<String>,
    pub support_bridges_per_patch: u32,
    pub merge_visible_fraction: Option<f64>,
    pub omega_budget_factor: Option<f64>,
    #[serde(default)]
    pub fab_size_in: Option<String>,
    #[serde(default)]
    pub frame_shape: FrameShape,
    #[serde(default)]
    pub dxf_frame_margin_mm: Option<f64>,
    #[serde(default)]
    pub dxf_setting_hole_diameter_mm: Option<f64>,
    #[serde(default)]
    pub dxf_setting_hole_inset_mm: Option<f64>,
    #[serde(default)]
    pub add_french_cleats: bool,
    #[serde(default)]
    pub create_etsy_release: bool,
    pub generate_composite_preview: bool,
    pub generate_showcase_preview: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CreateRunRequest {
    pub project_id: String,
    pub input_image_path: String,
    pub prompt: Option<String>,
    pub parameters: ParameterSnapshot,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RunSource {
    pub original_filename: String,
    pub input_path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PromptRef {
    pub path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OutputPaths {
    pub generator: String,
    pub postprocessed: String,
    pub final_output: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SavedRunSummary {
    pub schema_version: u32,
    pub run_id: String,
    pub project_id: String,
    pub status: RunStatus,
    pub created_at: String,
    pub started_at: Option<String>,
    pub finished_at: Option<String>,
    pub source: RunSource,
    pub prompt: Option<PromptRef>,
    pub parameters: ParameterSnapshot,
    pub outputs: OutputPaths,
    pub runtime_log_path: String,
    pub exit_code: Option<i32>,
}

#[cfg(test)]
mod tests {
    use super::{FrameShape, ParameterSnapshot};

    #[test]
    fn older_parameter_snapshots_default_to_rectangle() {
        let snapshot: ParameterSnapshot = serde_json::from_value(serde_json::json!({
            "stockSizeIn": null,
            "supportBridgesPerPatch": 5,
            "mergeVisibleFraction": null,
            "omegaBudgetFactor": null,
            "generateCompositePreview": true,
            "generateShowcasePreview": true
        }))
        .expect("older parameter snapshot should deserialize");

        assert_eq!(snapshot.frame_shape, FrameShape::Rectangle);
    }
}
