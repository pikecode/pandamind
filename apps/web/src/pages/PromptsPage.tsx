import { useCallback, useEffect, useState } from 'react';
import { apiDelete, apiGet, apiPost, apiPut } from '../lib/api';

interface Prompt {
  id: string;
  name: string;
  description: string | null;
  system: string | null;
  user_template: string | null;
  variables: PromptVariable[];
  tags: string[];
  version: number;
  created_at: string | null;
  updated_at: string | null;
}

interface PromptVariable {
  name: string;
  description?: string;
  default?: string;
  required?: boolean;
}

interface VersionSnapshot {
  version: number;
  snapshot: Record<string, unknown>;
  created_at: string | null;
}

export function PromptsPage() {
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Editor state
  const [editing, setEditing] = useState<Prompt | null>(null);
  const [editorDraft, setEditorDraft] = useState({
    name: '',
    description: '',
    system: '',
    user_template: '',
    tags: '',
  });

  // Variable panel
  const [variableValues, setVariableValues] = useState<Record<string, string>>({});
  const [renderedPreview, setRenderedPreview] = useState<{ system: string | null; user: string | null } | null>(null);

  // Version history
  const [versions, setVersions] = useState<VersionSnapshot[]>([]);
  const [showVersions, setShowVersions] = useState(false);

  // Create form
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', system: '', user_template: '', tags: '' });

  const fetchPrompts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiGet<Prompt[]>('/v1/prompts');
      setPrompts(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load prompts');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPrompts();
  }, [fetchPrompts]);

  // Detect variables from templates
  const detectVariables = (system: string, userTemplate: string): PromptVariable[] => {
    const VAR_RE = /\{\{(\w+)(?:\|([^}]+))?\}\}/g;
    const found = new Map<string, PromptVariable>();

    for (const text of [system, userTemplate]) {
      let m;
      while ((m = VAR_RE.exec(text)) !== null) {
        const name = m[1];
        if (!name) continue;
        if (!found.has(name)) {
          found.set(name, {
            name: name,
            default: m[2],
            required: !m[2],
          });
        }
      }
    }
    return Array.from(found.values());
  };

  // ---- Create ----
  const handleCreate = async () => {
    try {
      const variables = detectVariables(form.system, form.user_template);
      await apiPost('/v1/prompts', {
        name: form.name,
        description: form.description || null,
        system: form.system || null,
        user_template: form.user_template || null,
        variables,
        tags: form.tags.split(',').map((s) => s.trim()).filter(Boolean),
      });
      setFormOpen(false);
      setForm({ name: '', description: '', system: '', user_template: '', tags: '' });
      await fetchPrompts();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create prompt');
    }
  };

  // ---- Open editor ----
  const openEditor = (prompt: Prompt) => {
    setEditing(prompt);
    setEditorDraft({
      name: prompt.name,
      description: prompt.description ?? '',
      system: prompt.system ?? '',
      user_template: prompt.user_template ?? '',
      tags: prompt.tags.join(', '),
    });
    // Pre-fill variable values with defaults
    const vals: Record<string, string> = {};
    for (const v of prompt.variables) {
      vals[v.name] = v.default ?? '';
    }
    setVariableValues(vals);
    setRenderedPreview(null);
    setShowVersions(false);
    setVersions([]);
  };

  // ---- Save edits ----
  const handleSave = async () => {
    if (!editing) return;
    try {
      const variables = detectVariables(editorDraft.system, editorDraft.user_template);
      await apiPut(`/v1/prompts/${editing.id}`, {
        name: editorDraft.name,
        description: editorDraft.description || null,
        system: editorDraft.system || null,
        user_template: editorDraft.user_template || null,
        variables,
        tags: editorDraft.tags.split(',').map((s) => s.trim()).filter(Boolean),
      });
      await fetchPrompts();
      // Refresh editing state from updated list
      const updated = prompts.find((p) => p.id === editing.id);
      if (updated) openEditor({ ...updated, version: updated.version + 1 });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save prompt');
    }
  };

  // ---- Preview render ----
  const handlePreview = async () => {
    if (!editing) return;
    try {
      const res = await apiPost<{ system: string | null; user: string | null }>(
        `/v1/prompts/${editing.id}/render`,
        { variables: variableValues },
      );
      setRenderedPreview(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to render prompt');
    }
  };

  // ---- Version history ----
  const loadVersions = async () => {
    if (!editing) return;
    try {
      const data = await apiGet<VersionSnapshot[]>(`/v1/prompts/${editing.id}/versions`);
      setVersions(data);
      setShowVersions(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load versions');
    }
  };

  const handleRollback = async (version: number) => {
    if (!editing) return;
    if (!confirm(`Rollback to version ${version}? Current version will be saved as a snapshot.`)) return;
    try {
      await apiPost(`/v1/prompts/${editing.id}/rollback/${version}`, {});
      await fetchPrompts();
      setShowVersions(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to rollback');
    }
  };

  // ---- Delete ----
  const handleDelete = async (id: string) => {
    if (!confirm('Delete this prompt template?')) return;
    try {
      await apiDelete(`/v1/prompts/${id}`);
      if (editing?.id === id) setEditing(null);
      await fetchPrompts();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete prompt');
    }
  };

  // ---- Editor layout ----
  const editorVars = detectVariables(editorDraft.system, editorDraft.user_template);

  return (
    <div className="flex h-full gap-4">
      {/* Left: prompt list */}
      <div className="w-72 shrink-0 border-r border-zinc-200 pr-4 dark:border-zinc-700">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Prompts</h2>
          <button
            onClick={() => setFormOpen(true)}
            className="rounded bg-zinc-900 px-3 py-1.5 text-xs text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            + New
          </button>
        </div>

        {error && (
          <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
            {error}
          </div>
        )}

        {formOpen && (
          <div className="mb-3 rounded border border-zinc-200 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-800">
            <input
              className="mb-2 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-700"
              placeholder="Name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <input
              className="mb-2 w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-700"
              placeholder="Tags (comma-separated)"
              value={form.tags}
              onChange={(e) => setForm({ ...form, tags: e.target.value })}
            />
            <div className="flex gap-2">
              <button
                onClick={handleCreate}
                className="rounded bg-zinc-900 px-3 py-1.5 text-xs text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900"
              >
                Save
              </button>
              <button
                onClick={() => setFormOpen(false)}
                className="rounded border border-zinc-300 px-3 py-1.5 text-xs hover:bg-zinc-100 dark:border-zinc-600 dark:hover:bg-zinc-700"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {loading ? (
          <p className="text-sm text-zinc-500">Loading...</p>
        ) : prompts.length === 0 ? (
          <p className="text-sm text-zinc-500">No prompts yet.</p>
        ) : (
          <div className="space-y-1">
            {prompts.map((p) => (
              <div
                key={p.id}
                className={`group flex cursor-pointer items-center justify-between rounded px-3 py-2 text-sm transition ${
                  editing?.id === p.id
                    ? 'bg-zinc-100 font-medium dark:bg-zinc-700'
                    : 'hover:bg-zinc-50 dark:hover:bg-zinc-800'
                }`}
                onClick={() => openEditor(p)}
              >
                <div className="min-w-0">
                  <div className="truncate">{p.name}</div>
                  <div className="text-xs text-zinc-400">v{p.version}</div>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); handleDelete(p.id); }}
                  className="ml-2 hidden rounded px-1.5 py-0.5 text-xs text-red-500 hover:bg-red-50 group-hover:inline-block dark:hover:bg-red-900/20"
                >
                  Del
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Right: editor */}
      {!editing ? (
        <div className="flex flex-1 items-center justify-center text-sm text-zinc-400">
          Select a prompt to edit, or create a new one.
        </div>
      ) : (
        <div className="flex min-w-0 flex-1 flex-col gap-4 overflow-auto">
          {/* Name + meta */}
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <label className="mb-1 block text-xs text-zinc-500">Name</label>
              <input
                className="w-full rounded border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-800"
                value={editorDraft.name}
                onChange={(e) => setEditorDraft({ ...editorDraft, name: e.target.value })}
              />
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-xs text-zinc-500">Tags</label>
              <input
                className="w-full rounded border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-800"
                placeholder="comma-separated"
                value={editorDraft.tags}
                onChange={(e) => setEditorDraft({ ...editorDraft, tags: e.target.value })}
              />
            </div>
            <div className="flex gap-2 pb-0.5">
              <button
                onClick={handleSave}
                className="rounded bg-zinc-900 px-4 py-2 text-sm text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900"
              >
                Save
              </button>
              <button
                onClick={loadVersions}
                className="rounded border border-zinc-300 px-3 py-2 text-sm hover:bg-zinc-100 dark:border-zinc-600 dark:hover:bg-zinc-700"
              >
                History
              </button>
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="mb-1 block text-xs text-zinc-500">Description</label>
            <input
              className="w-full rounded border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-800"
              placeholder="Optional description"
              value={editorDraft.description}
              onChange={(e) => setEditorDraft({ ...editorDraft, description: e.target.value })}
            />
          </div>

          {/* Template editors */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-xs text-zinc-500">System Prompt</label>
              <textarea
                className="h-40 w-full resize-y rounded border border-zinc-300 px-3 py-2 font-mono text-sm dark:border-zinc-600 dark:bg-zinc-800"
                placeholder="You are a helpful assistant."
                value={editorDraft.system}
                onChange={(e) => setEditorDraft({ ...editorDraft, system: e.target.value })}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-zinc-500">User Template</label>
              <textarea
                className="h-40 w-full resize-y rounded border border-zinc-300 px-3 py-2 font-mono text-sm dark:border-zinc-600 dark:bg-zinc-800"
                placeholder="Translate the following to {{language}}: {{text}}"
                value={editorDraft.user_template}
                onChange={(e) => setEditorDraft({ ...editorDraft, user_template: e.target.value })}
              />
            </div>
          </div>

          {/* Version history panel */}
          {showVersions && (
            <div className="rounded border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/50">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-semibold">Version History</h3>
                <button
                  onClick={() => setShowVersions(false)}
                  className="text-xs text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
                >
                  Close
                </button>
              </div>
              {versions.length === 0 ? (
                <p className="text-xs text-zinc-500">No previous versions.</p>
              ) : (
                <div className="max-h-48 space-y-2 overflow-auto">
                  {versions.map((v) => (
                    <div
                      key={v.version}
                      className="flex items-center justify-between rounded border border-zinc-200 bg-white px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-700"
                    >
                      <div>
                        <span className="font-medium">v{v.version}</span>
                        {v.created_at && (
                          <span className="ml-2 text-xs text-zinc-400">
                            {new Date(v.created_at).toLocaleString()}
                          </span>
                        )}
                      </div>
                      <button
                        onClick={() => handleRollback(v.version)}
                        className="rounded border border-zinc-300 px-2 py-0.5 text-xs hover:bg-zinc-100 dark:border-zinc-600 dark:hover:bg-zinc-600"
                      >
                        Restore
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Variable panel */}
          {editorVars.length > 0 && (
            <div className="rounded border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/50">
              <h3 className="mb-3 text-sm font-semibold">Variables</h3>
              <div className="grid grid-cols-2 gap-3">
                {editorVars.map((v) => (
                  <div key={v.name}>
                    <label className="mb-1 flex items-center gap-1 text-xs text-zinc-600 dark:text-zinc-400">
                      <span className="font-mono">{`{{${v.name}}}`}</span>
                      {v.required && <span className="text-red-500">*</span>}
                      {v.default && (
                        <span className="text-zinc-400">(default: {v.default})</span>
                      )}
                    </label>
                    <input
                      className="w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-700"
                      placeholder={v.description ?? v.name}
                      value={variableValues[v.name] ?? ''}
                      onChange={(e) =>
                        setVariableValues({ ...variableValues, [v.name]: e.target.value })
                      }
                    />
                  </div>
                ))}
              </div>
              <button
                onClick={handlePreview}
                className="mt-3 rounded bg-zinc-800 px-4 py-1.5 text-xs text-white hover:bg-zinc-700 dark:bg-zinc-200 dark:text-zinc-900 dark:hover:bg-zinc-300"
              >
                Preview Render
              </button>
            </div>
          )}

          {/* Rendered preview */}
          {renderedPreview && (
            <div className="rounded border border-green-200 bg-green-50 p-4 dark:border-green-800 dark:bg-green-900/20">
              <h3 className="mb-2 text-sm font-semibold text-green-800 dark:text-green-300">
                Rendered Output
              </h3>
              {renderedPreview.system && (
                <div className="mb-2">
                  <div className="text-xs font-medium text-green-700 dark:text-green-400">System</div>
                  <pre className="mt-1 whitespace-pre-wrap rounded bg-white p-2 text-sm dark:bg-zinc-800">
                    {renderedPreview.system}
                  </pre>
                </div>
              )}
              {renderedPreview.user && (
                <div>
                  <div className="text-xs font-medium text-green-700 dark:text-green-400">User</div>
                  <pre className="mt-1 whitespace-pre-wrap rounded bg-white p-2 text-sm dark:bg-zinc-800">
                    {renderedPreview.user}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
