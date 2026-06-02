import { useCallback, useEffect, useState } from 'react';
import { apiGet, apiPost, apiDelete } from '../lib/api';

interface ModelConfig {
  id: string;
  name: string;
  provider: string;
  model: string;
  base_url: string | null;
  api_key: string | null;
  default_params: Record<string, unknown>;
  aliases: string[];
  enabled: boolean;
}

const PROVIDERS = [
  { value: 'ollama', label: 'Ollama (Local)' },
  { value: 'openai-compatible', label: 'OpenAI Compatible' },
];

export function ModelsPage() {
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState({
    name: '',
    provider: 'ollama',
    model: '',
    base_url: '',
    api_key: '',
    aliases: '',
  });

  const fetchModels = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiGet<ModelConfig[]>('/v1/models');
      setModels(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load models');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  const handleCreate = async () => {
    try {
      await apiPost('/v1/models', {
        name: form.name,
        provider: form.provider,
        model: form.model,
        base_url: form.base_url || null,
        api_key: form.api_key || null,
        default_params: { temperature: 0.7 },
        aliases: form.aliases.split(',').map((s) => s.trim()).filter(Boolean),
        enabled: true,
      });
      setFormOpen(false);
      setForm({ name: '', provider: 'ollama', model: '', base_url: '', api_key: '', aliases: '' });
      await fetchModels();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create model');
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this model configuration?')) return;
    try {
      await apiDelete(`/v1/models/${id}`);
      await fetchModels();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete model');
    }
  };

  const handlePing = async (id: string) => {
    try {
      const res = await apiGet<{ health: { status: string; message?: string; latency_ms?: number } }>(`/v1/models/${id}/ping`);
      alert(`Ping ${id}: ${res.health.status} (${res.health.latency_ms ?? '-'}ms)`);
    } catch (e) {
      alert(`Ping ${id} failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-xl font-semibold">Models</h2>
        <button
          onClick={() => setFormOpen(true)}
          className="rounded bg-zinc-900 px-4 py-2 text-sm text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          + Add Model
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      )}

      {formOpen && (
        <div className="mb-6 rounded border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-800">
          <h3 className="mb-3 text-sm font-semibold">New Model</h3>
          <div className="grid grid-cols-2 gap-3">
            <input
              className="rounded border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-700"
              placeholder="Name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <select
              className="rounded border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-700"
              value={form.provider}
              onChange={(e) => setForm({ ...form, provider: e.target.value })}
            >
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
            <input
              className="rounded border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-700"
              placeholder="Model (e.g. llama3:8b, gpt-4o)"
              value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })}
            />
            <input
              className="rounded border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-700"
              placeholder="Base URL (optional)"
              value={form.base_url}
              onChange={(e) => setForm({ ...form, base_url: e.target.value })}
            />
            <input
              className="rounded border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-700"
              placeholder="API Key (optional)"
              type="password"
              value={form.api_key}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })}
            />
            <input
              className="rounded border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-700"
              placeholder="Aliases (comma-separated)"
              value={form.aliases}
              onChange={(e) => setForm({ ...form, aliases: e.target.value })}
            />
          </div>
          <div className="mt-3 flex gap-2">
            <button
              onClick={handleCreate}
              className="rounded bg-zinc-900 px-4 py-2 text-sm text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
            >
              Save
            </button>
            <button
              onClick={() => setFormOpen(false)}
              className="rounded border border-zinc-300 px-4 py-2 text-sm hover:bg-zinc-100 dark:border-zinc-600 dark:hover:bg-zinc-700"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="text-sm text-zinc-500">Loading...</p>
      ) : models.length === 0 ? (
        <p className="text-sm text-zinc-500">No models configured.</p>
      ) : (
        <div className="space-y-3">
          {models.map((m) => (
            <div
              key={m.id}
              className="flex items-center justify-between rounded border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-800"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{m.name}</span>
                  <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300">
                    {m.provider}
                  </span>
                  <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300">
                    {m.model}
                  </span>
                </div>
                <div className="mt-1 text-xs text-zinc-500">
                  {m.base_url && <span className="mr-3">{m.base_url}</span>}
                  {m.api_key && <span>Key: {m.api_key}</span>}
                </div>
                {m.aliases.length > 0 && (
                  <div className="mt-1 text-xs text-zinc-400">
                    aliases: {m.aliases.join(', ')}
                  </div>
                )}
              </div>
              <div className="flex shrink-0 gap-2">
                <button
                  onClick={() => handlePing(m.id)}
                  className="rounded border border-zinc-300 px-3 py-1 text-xs hover:bg-zinc-100 dark:border-zinc-600 dark:hover:bg-zinc-700"
                >
                  Ping
                </button>
                <button
                  onClick={() => handleDelete(m.id)}
                  className="rounded border border-red-200 px-3 py-1 text-xs text-red-600 hover:bg-red-50 dark:border-red-800 dark:hover:bg-red-900/20"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
