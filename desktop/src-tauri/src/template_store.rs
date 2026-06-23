use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TemplateDoc {
    pub filename: String,
    pub name: String,
    pub family: String,
    pub subject: String,
    pub color_count: i64,
    pub color_list: String,
    pub structural_element: String,
    pub background_color: String,
    pub extra_notes: String,
    pub system_prompt_suffix: String,
    pub body: String,
    pub updated_at_epoch: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TemplateDraft {
    pub name: String,
    pub family: String,
    pub subject: String,
    pub color_count: i64,
    pub color_list: String,
    pub structural_element: String,
    pub background_color: String,
    pub extra_notes: String,
    pub system_prompt_suffix: String,
    pub body: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SaveTemplatePayload {
    pub existing_filename: Option<String>,
    pub template: TemplateDraft,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct Frontmatter {
    name: String,
    family: String,
    subject: String,
    color_count: i64,
    color_list: String,
    structural_element: String,
    background_color: String,
    extra_notes: String,
    system_prompt_suffix: String,
}

fn repo_root() -> Result<PathBuf, String> {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .map_err(|e| format!("Could not resolve repo root: {e}"))
}

fn templates_dir() -> Result<PathBuf, String> {
    let dir = repo_root()?.join("image_gen_prompts").join("templates");
    fs::create_dir_all(&dir).map_err(|e| format!("Could not create templates dir: {e}"))?;
    Ok(dir)
}

fn now_epoch() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

fn slugify_name(name: &str) -> String {
    let mut out = String::new();
    let mut prev_dash = false;

    for c in name.trim().to_lowercase().chars() {
        if c.is_ascii_alphanumeric() {
            out.push(c);
            prev_dash = false;
        } else if !prev_dash {
            out.push('-');
            prev_dash = true;
        }
    }

    let out = out.trim_matches('-').to_string();
    if out.is_empty() {
        "template".to_string()
    } else {
        out
    }
}

fn sanitize_filename(input: &str) -> String {
    Path::new(input)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("template.md")
        .to_string()
}

fn parse_template_file(path: &Path) -> Result<TemplateDoc, String> {
    let raw = fs::read_to_string(path).map_err(|e| format!("Failed to read template: {e}"))?;
    let filename = path.file_name().and_then(|s| s.to_str()).unwrap_or("").to_string();

    let (fm, body) = if raw.starts_with("---\n") {
        if let Some(end_idx) = raw[4..].find("\n---\n") {
            let real_end = 4 + end_idx;
            let yaml = &raw[4..real_end];
            let body = raw[(real_end + 5)..].trim().to_string();
            let parsed: Frontmatter = serde_yaml::from_str(yaml)
                .map_err(|e| format!("Invalid frontmatter in {filename}: {e}"))?;
            (parsed, body)
        } else {
            return Err(format!("Template {filename} has malformed frontmatter"));
        }
    } else {
        (
            Frontmatter {
                name: filename.trim_end_matches(".md").to_string(),
                family: "custom".to_string(),
                subject: "".to_string(),
                color_count: 4,
                color_list: "".to_string(),
                structural_element: "bands".to_string(),
                background_color: "solid white".to_string(),
                extra_notes: "".to_string(),
                system_prompt_suffix: "".to_string(),
            },
            raw.trim().to_string(),
        )
    };

    let updated_at_epoch = fs::metadata(path)
        .ok()
        .and_then(|m| m.modified().ok())
        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|d| d.as_secs() as i64)
        .unwrap_or_else(now_epoch);

    Ok(TemplateDoc {
        filename,
        name: fm.name,
        family: fm.family,
        subject: fm.subject,
        color_count: fm.color_count,
        color_list: fm.color_list,
        structural_element: fm.structural_element,
        background_color: fm.background_color,
        extra_notes: fm.extra_notes,
        system_prompt_suffix: fm.system_prompt_suffix,
        body,
        updated_at_epoch,
    })
}

#[tauri::command]
pub fn list_templates() -> Result<Vec<TemplateDoc>, String> {
    let dir = templates_dir()?;
    let mut docs = Vec::new();

    for entry in fs::read_dir(&dir).map_err(|e| format!("Failed to read templates dir: {e}"))? {
        let entry = entry.map_err(|e| format!("Failed to read dir entry: {e}"))?;
        let path = entry.path();
        if path.is_file()
            && path
                .extension()
                .and_then(|e| e.to_str())
                .map(|e| e.eq_ignore_ascii_case("md"))
                .unwrap_or(false)
        {
            docs.push(parse_template_file(&path)?);
        }
    }

    docs.sort_by(|a, b| a.name.to_lowercase().cmp(&b.name.to_lowercase()));
    Ok(docs)
}

#[tauri::command]
pub fn save_template(payload: SaveTemplatePayload) -> Result<TemplateDoc, String> {
    if payload.template.name.trim().is_empty() {
        return Err("Template name is required.".to_string());
    }

    if payload.template.color_count < 3 || payload.template.color_count > 5 {
        return Err("colorCount must be between 3 and 5.".to_string());
    }

    let dir = templates_dir()?;

    let target_name = format!("{}.md", slugify_name(&payload.template.name));
    let target_path = dir.join(&target_name);

    let frontmatter = Frontmatter {
        name: payload.template.name.trim().to_string(),
        family: payload.template.family.trim().to_string(),
        subject: payload.template.subject.trim().to_string(),
        color_count: payload.template.color_count,
        color_list: payload.template.color_list.trim().to_string(),
        structural_element: payload.template.structural_element.trim().to_string(),
        background_color: payload.template.background_color.trim().to_string(),
        extra_notes: payload.template.extra_notes.trim().to_string(),
        system_prompt_suffix: payload.template.system_prompt_suffix.trim().to_string(),
    };

    let yaml = serde_yaml::to_string(&frontmatter)
        .map_err(|e| format!("Failed to serialize frontmatter: {e}"))?;
    let yaml = yaml.strip_prefix("---\n").unwrap_or(&yaml);

    let body = payload.template.body.trim().to_string();
    let composed = format!("---\n{}---\n\n{}\n", yaml, body);

    fs::write(&target_path, composed).map_err(|e| format!("Failed to write template: {e}"))?;

    if let Some(existing) = payload.existing_filename {
        let old = sanitize_filename(&existing);
        if old != target_name {
            let old_path = dir.join(old);
            if old_path.exists() {
                let _ = fs::remove_file(old_path);
            }
        }
    }

    parse_template_file(&target_path)
}

#[tauri::command]
pub fn delete_template(filename: String) -> Result<(), String> {
    let dir = templates_dir()?;
    let safe = sanitize_filename(&filename);
    let path = dir.join(safe);

    if !path.exists() {
        return Ok(());
    }

    fs::remove_file(path).map_err(|e| format!("Failed to delete template: {e}"))?;
    Ok(())
}

