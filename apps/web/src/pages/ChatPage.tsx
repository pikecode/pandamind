import { useCallback, useEffect, useRef, useState } from 'react';
import { apiGet } from '../lib/api';

function getAuthHeader(): Record<string, string> {
  const token = localStorage.getItem('pm_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

interface ModelConfig {
  id: string;
  name: string;
  provider: string;
}

interface PromptTemplate {
  id: string;
  name: string;
  description: string | null;
  system: string | null;
  user_template: string | null;
  variables: PromptVariable[];
  tags: string[];
  version: number;
}

interface PromptVariable {
  name: string;
  description?: string;
  default?: string;
  required?: boolean;
}

export function ChatPage() {
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [selectedModel, setSelectedModel] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Prompt template state
  const [prompts, setPrompts] = useState<PromptTemplate[]>([]);
  const [selectedPromptId, setSelectedPromptId] = useState('');
  const [promptVars, setPromptVars] = useState<Record<string, string>>({});

  useEffect(() => {
    apiGet<ModelConfig[]>('/v1/models').then(setModels).catch(() => {});
    apiGet<PromptTemplate[]>('/v1/prompts').then(setPrompts).catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const selectedPrompt = prompts.find((p) => p.id === selectedPromptId);

  const handlePromptSelect = (promptId: string) => {
    setSelectedPromptId(promptId);
    const prompt = prompts.find((p) => p.id === promptId);
    if (prompt) {
      const vars: Record<string, string> = {};
      for (const v of prompt.variables) {
        vars[v.name] = v.default ?? '';
      }
      setPromptVars(vars);
    } else {
      setPromptVars({});
    }
  };

  const handleSend = useCallback(async () => {
    if (!input.trim() || !selectedModel || streaming) return;

    const userMsg: Message = { role: 'user', content: input.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setStreaming(true);

    const abort = new AbortController();
    abortRef.current = abort;

    // Build messages array, injecting system prompt + template if selected
    const chatMessages: { role: string; content: string }[] = [];

    // Inject system message from prompt template if selected
    if (selectedPrompt?.system) {
      const renderedSystem = selectedPrompt.system.replace(
        /\{\{(\w+)(?:\|([^}]+))?\}\}/g,
        (_, name: string, defaultVal: string | undefined) => promptVars[name] || defaultVal || `{{${name}}}`,
      );
      chatMessages.push({ role: 'system', content: renderedSystem });
    }

    // Existing conversation history
    for (const m of [...messages, userMsg]) {
      chatMessages.push({ role: m.role, content: m.content });
    }

    try {
      const response = await fetch('/api/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
        body: JSON.stringify({
          model: selectedModel,
          messages: chatMessages,
          stream: true,
        }),
        signal: abort.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let assistantContent = '';

      setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

      while (reader) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6);
          if (data === '[DONE]') continue;

          try {
            const parsed = JSON.parse(data);
            const delta = parsed.choices?.[0]?.delta?.content;
            if (delta) {
              assistantContent += delta;
              setMessages((prev) => {
                const newMessages = [...prev];
                const last = newMessages[newMessages.length - 1];
                if (last && last.role === 'assistant') {
                  last.content = assistantContent;
                }
                return newMessages;
              });
            }
          } catch {
            // Ignore parse errors for malformed chunks
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: `Error: ${err.message}` },
        ]);
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, [input, selectedModel, streaming, messages, selectedPrompt, promptVars]);

  const handleStop = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header row: model + prompt selectors */}
      <div className="mb-4 flex items-center gap-3">
        <h2 className="text-xl font-semibold">Chat</h2>
        <select
          className="rounded border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-700"
          value={selectedModel}
          onChange={(e) => setSelectedModel(e.target.value)}
        >
          <option value="">Select model...</option>
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>

        <select
          className="rounded border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-700"
          value={selectedPromptId}
          onChange={(e) => handlePromptSelect(e.target.value)}
        >
          <option value="">No prompt template</option>
          {prompts.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      {/* Prompt variable inputs */}
      {selectedPrompt && selectedPrompt.variables.length > 0 && (
        <div className="mb-3 rounded border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-700 dark:bg-zinc-800/50">
          <div className="mb-2 text-xs font-medium text-zinc-500">Template Variables</div>
          <div className="flex flex-wrap gap-3">
            {selectedPrompt.variables.map((v) => (
              <div key={v.name} className="min-w-[140px]">
                <label className="mb-0.5 flex items-center gap-1 text-xs text-zinc-600 dark:text-zinc-400">
                  <span className="font-mono">{`{{${v.name}}}`}</span>
                  {v.required && !v.default && <span className="text-red-500">*</span>}
                </label>
                <input
                  className="w-full rounded border border-zinc-300 px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-700"
                  placeholder={v.description ?? v.name}
                  value={promptVars[v.name] ?? ''}
                  onChange={(e) => setPromptVars({ ...promptVars, [v.name]: e.target.value })}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto rounded border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-800">
        {messages.length === 0 ? (
          <p className="text-center text-sm text-zinc-400">Start a conversation...</p>
        ) : (
          messages.map((msg, i) => (
            <div
              key={i}
              className={`mb-3 max-w-[80%] rounded-lg px-4 py-2 ${
                msg.role === 'user'
                  ? 'ml-auto bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                  : 'mr-auto bg-zinc-100 text-zinc-900 dark:bg-zinc-700 dark:text-zinc-100'
              }`}
            >
              <pre className="whitespace-pre-wrap text-sm">{msg.content}</pre>
              {streaming && msg.role === 'assistant' && msg.content === '' && (
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-zinc-400" />
              )}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="mt-4 flex gap-2">
        <textarea
          className="flex-1 resize-none rounded border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-700"
          rows={2}
          placeholder={selectedModel ? 'Type a message...' : 'Select a model first'}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={!selectedModel || streaming}
        />
        <div className="flex flex-col gap-2">
          {streaming ? (
            <button
              onClick={handleStop}
              className="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700"
            >
              Stop
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!selectedModel || !input.trim()}
              className="rounded bg-zinc-900 px-4 py-2 text-sm text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
            >
              Send
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
