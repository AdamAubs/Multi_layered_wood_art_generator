import { useEffect, useMemo, useState } from "react";
import { useTemplates } from "../hooks/useTemplates";
import { TemplateDoc, TemplateDraft, TemplateFamily } from "../types/library";
import "../styles/template-library.css";

interface TemplateLibraryPageProps {
  onBackToGenerator: () => void;
}

const familyOptions: { value: TemplateFamily; label: string }[] = [
  { value: "radial-mandala", label: "Radial Mandala" },
  { value: "skyline-architecture", label: "Skyline / Architecture" },
  { value: "flag-emblem", label: "Flag + Emblem" },
  { value: "wreath", label: "Wreath" },
  { value: "dense-field", label: "Dense Field" },
  { value: "custom", label: "Custom" },
];

function familyStarterBody(family: TemplateFamily): string {
  if (family === "radial-mandala") {
    return "A square radial knotwork composition with {{subject}} at center and thick interlocking bands touching all four edges.";
  }
  if (family === "skyline-architecture") {
    return "A bold skyline silhouette composition with {{subject}}, thick structural masses, and connected foreground base touching the canvas edges.";
  }
  if (family === "flag-emblem") {
    return "A connected emblem composition featuring {{subject}}, large closed shapes, and no isolated floating details.";
  }
  if (family === "wreath") {
    return "A connected wreath composition with {{subject}} centered and a thick outer ring touching all four edges.";
  }
  if (family === "dense-field") {
    return "A dense edge-to-edge field composition featuring {{subject}} with continuous connectivity and no empty background gaps.";
  }
  return "A square, connected, flat-color MWCA-ready composition featuring {{subject}}.";
}

function buildPrompt(draft: TemplateDraft): string {
  const safeLabel = draft.colorCount <= 4 ? "Safe mode" : "Standard mode";
  const body = draft.body || familyStarterBody(draft.family);

  return [
    body.replace("{{subject}}", draft.subject || "main subject"),
    `Exactly ${draft.colorCount} flat solid colors: ${draft.colorList || "deep charcoal, warm ivory, forest green, caramel brown"}.`,
    `Primary structural element: ${draft.structuralElement || "bands"}, thick and uniform with no thin sections anywhere.`,
    draft.extraNotes ? `Additional notes: ${draft.extraNotes}` : "",
    `${safeLabel}. Bold black outlines separating every region, no thin isolated traces, completely flat fill areas, no gradients no shading no texture no photorealism, clean paint-by-numbers vector style, solid ${draft.backgroundColor || "white"} background.`,
    draft.systemPromptSuffix || "",
  ]
    .filter(Boolean)
    .join("\n\n");
}

export function TemplateLibraryPage({
  onBackToGenerator,
}: TemplateLibraryPageProps) {
  const { templates, isLoading, error, refresh, save, remove, emptyDraft } =
    useTemplates();

  const [selectedFilename, setSelectedFilename] = useState<string | null>(null);
  const [draft, setDraft] = useState<TemplateDraft>(emptyDraft);
  console.log(draft);
  const [localError, setLocalError] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);

  useEffect(() => {
    refresh().catch((e) => setLocalError(String(e)));
  }, [refresh]);

  const selected = useMemo<TemplateDoc | null>(
    () => templates.find((t) => t.filename === selectedFilename) ?? null,
    [templates, selectedFilename],
  );

  useEffect(() => {
    if (selected) {
      const {
        filename: _filename,
        updatedAtEpoch: _updated,
        ...rest
      } = selected;
      setDraft(rest);
    }
  }, [selected]);

  function newTemplate() {
    setSelectedFilename(null);
    setDraft({
      ...emptyDraft,
      body: familyStarterBody("radial-mandala"),
      name: "New Template",
    });
  }

  async function saveCurrent() {
    setLocalError("");
    if (!draft.name.trim()) {
      setLocalError("Template name is required.");
      return;
    }
    if (draft.colorCount < 3 || draft.colorCount > 5) {
      setLocalError("Color count must be between 3 and 5.");
      return;
    }

    const saved = await save(draft, selectedFilename ?? undefined);
    setSelectedFilename(saved.filename);
  }

  async function deleteCurrent() {
    if (!selectedFilename) return;
    await remove(selectedFilename);
    setSelectedFilename(null);
    setDraft(emptyDraft);
  }

  return (
    <section className="tpl-page">
      <div className="tpl-header">
        <h1>Prompt Library</h1>
        <button onClick={onBackToGenerator}>Back To Generator</button>
      </div>

      <div className="tpl-grid">
        <aside className="tpl-list">
          <div className="tpl-list-header">
            <h2>Templates</h2>
            <button onClick={newTemplate}>New</button>
          </div>

          {isLoading && <p>Loading templates...</p>}
          {error && <p className="tpl-error">{error}</p>}

          {!isLoading && templates.length === 0 && <p>No templates yet.</p>}

          <ul>
            {templates.map((t) => (
              <li key={t.filename}>
                <button
                  className={
                    selectedFilename === t.filename ? "tpl-active" : ""
                  }
                  onClick={() => setSelectedFilename(t.filename)}
                >
                  {t.name}
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <div className="tpl-editor">
          <h2>{selectedFilename ? "Edit Template" : "Create Template"}</h2>

          <label>
            Name
            <input
              value={draft.name}
              onChange={(e) =>
                setDraft((d) => ({ ...d, name: e.target.value }))
              }
            />
          </label>

          <label>
            Family
            <select
              value={draft.family}
              onChange={(e) => {
                const family = e.target.value as TemplateFamily;
                setDraft((d) => ({
                  ...d,
                  family,
                  body: familyStarterBody(family),
                }));
                console.log(draft);
                buildPrompt(draft);
              }}
            >
              {familyOptions.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Subject
            <input
              value={draft.subject}
              onChange={(e) =>
                setDraft((d) => ({ ...d, subject: e.target.value }))
              }
            />
          </label>

          <label>
            Color Count (3-5)
            <input
              type="number"
              min={3}
              max={5}
              value={draft.colorCount}
              onChange={(e) =>
                setDraft((d) => ({
                  ...d,
                  colorCount: Number(e.target.value || 4),
                }))
              }
            />
          </label>

          <label>
            Color List
            <input
              value={draft.colorList}
              onChange={(e) =>
                setDraft((d) => ({ ...d, colorList: e.target.value }))
              }
              placeholder="deep charcoal, ivory, forest green, caramel brown"
            />
          </label>

          <label>
            Structural Element
            <input
              value={draft.structuralElement}
              onChange={(e) =>
                setDraft((d) => ({ ...d, structuralElement: e.target.value }))
              }
            />
          </label>

          <label>
            Background Color
            <input
              value={draft.backgroundColor}
              onChange={(e) =>
                setDraft((d) => ({ ...d, backgroundColor: e.target.value }))
              }
            />
          </label>

          <label>
            Extra Notes
            <textarea
              rows={3}
              value={draft.extraNotes}
              onChange={(e) =>
                setDraft((d) => ({ ...d, extraNotes: e.target.value }))
              }
            />
          </label>

          <label>
            Template Body
            <textarea
              rows={6}
              value={draft.body}
              onChange={(e) =>
                setDraft((d) => ({ ...d, body: e.target.value }))
              }
            />
          </label>

          <button
            className="tpl-toggle"
            onClick={() => setShowAdvanced((v) => !v)}
            type="button"
          >
            {showAdvanced ? "Hide Advanced" : "Show Advanced"}
          </button>

          {showAdvanced && (
            <label>
              System Prompt Suffix (hidden helper block)
              <textarea
                rows={4}
                value={draft.systemPromptSuffix}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    systemPromptSuffix: e.target.value,
                  }))
                }
              />
            </label>
          )}

          <div className="tpl-actions">
            <button onClick={saveCurrent}>Save</button>
            <button onClick={newTemplate}>Reset</button>
            <button disabled={!selectedFilename} onClick={deleteCurrent}>
              Delete
            </button>
          </div>

          {localError && <p className="tpl-error">{localError}</p>}
        </div>

        <div className="tpl-preview">
          <h2>Prompt Preview</h2>
          <pre>{buildPrompt(draft)}</pre>
        </div>
      </div>
    </section>
  );
}
