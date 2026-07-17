# Current Milestone

## Project Run Capture and Library Browser

## Goal

Build one complete vertical slice:

```text
Choose or create project
    ↓
Choose input image
    ↓
Optionally enter image-generation prompt
    ↓
Configure existing parameters
    ↓
Start generator
    ↓
Save complete run
    ↓
Browse saved run in Library page
```

The milestone succeeds when the application can save runs and rediscover them after restarting.

---

## In scope

### Generator page

Add:

- Existing-project selector.
- New-project creation.
- Optional image-generation prompt field.
- Existing image browser.
- Existing parameter controls.
- Start Run action.

### Tauri backend

Add:

- Library initialization.
- Project creation.
- Project discovery.
- Unique run allocation.
- Input copying.
- Optional prompt saving.
- Minimal `run.json` writing.
- Runtime-log saving.
- Output-directory copying.
- Completed and failed status updates.

### Library page

Display:

- Projects.
- Runs under each project.
- Run status.
- Input filename.
- Prompt saved or not saved.
- Parameter values.
- Output paths.
- Runtime-log path.

Add actions to open:

- Run folder.
- Final output folder.

---

## Out of scope

Do not implement:

- Reusable prompt-library integration.
- Prompt versioning.
- Input hashes.
- Input deduplication.
- Configurable library locations.
- Direct Python output destinations.
- Quality inspection.
- Pass or fail decisions.
- Annotations.
- DXF rendering.
- Full image galleries.
- Search and filters.
- Trend analysis.
- Fabrication tracking.
- Etsy preparation.
- Cloud synchronization.

---

## Implementation checkpoints

### Checkpoint 1 — Library initialization

Create:

```text
LazyLayerzzzLibrary/
├── vault.json
└── projects/
```

Verify:

- The operation is safe to run repeatedly.
- The library is ignored by Git.
- `vault.json` contains valid JSON.

### Checkpoint 2 — Project creation

Support:

- Creating a project.
- Generating a safe slug.
- Listing existing projects.
- Rejecting duplicate project IDs.

Verify:

- Projects survive an application restart.
- Duplicate creation does not overwrite files.

### Checkpoint 3 — Optional prompt field

Support:

- Multiline prompt input.
- Empty or whitespace-only prompts.
- Runs without prompts.

Verify:

- The prompt is not required.
- The prompt is not sent to Python.

### Checkpoint 4 — Saved run creation

Before starting Python:

- Allocate a unique run ID.
- Create run folders.
- Copy the selected input.
- Save the optional prompt.
- Save parameters.
- Write pending and running status.

Verify:

- Two runs never share a directory.
- A run without a prompt has no `prompt.md`.

### Checkpoint 5 — Capture result

After Python finishes:

- Save the runtime log.
- Copy generated outputs.
- Copy nested preview directories.
- Record completed or failed status.
- Record the exit code.

Verify:

- Failed runs remain saved.
- Previous runs remain unchanged.

### Checkpoint 6 — Library page

Read projects and runs from disk.

Verify:

- The page does not depend on the most recent React job.
- Saved runs appear after restarting the application.
- Run folders can be opened from the UI.

---

## End-to-end acceptance test

The milestone is complete when this sequence passes:

- [ ] Start the desktop application.
- [ ] Create a project called `Tomorrow Test`.
- [ ] Browse for an input image.
- [ ] Enter an image-generation prompt.
- [ ] Change at least two pipeline parameters.
- [ ] Start the run.
- [ ] Confirm a unique run directory exists.
- [ ] Confirm the input was copied into `source/`.
- [ ] Confirm the prompt was saved as `source/prompt.md`.
- [ ] Confirm `run.json` contains the selected parameters.
- [ ] Confirm the Python pipeline executes.
- [ ] Confirm the runtime log is saved.
- [ ] Confirm generator outputs were copied.
- [ ] Confirm postprocessed outputs were copied.
- [ ] Confirm final outputs were copied.
- [ ] Confirm nested previews were copied.
- [ ] Open the Library page.
- [ ] Confirm the project and run appear.
- [ ] Close and restart the application.
- [ ] Confirm the saved project and run still appear.
- [ ] Start another run in the same project without a prompt.
- [ ] Confirm the first run is unchanged.
- [ ] Confirm the second run has no `prompt.md`.
- [ ] Confirm both runs appear in the Library page.

---

## Completion rule

Do not expand this milestone while implementing it.

The next feature should begin only after the complete end-to-end test passes.
