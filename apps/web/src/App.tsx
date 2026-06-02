import { useState } from 'react';
import { NavLink, Route, Routes, Navigate } from 'react-router-dom';
import { ChatPage } from './pages/ChatPage';
import { ModelsPage } from './pages/ModelsPage';
import { PromptsPage } from './pages/PromptsPage';
import { LoginPage } from './pages/LoginPage';

const navItems = [
  { to: '/chat', label: 'Chat' },
  { to: '/models', label: 'Models' },
  { to: '/prompts', label: 'Prompts' },
];

export function App() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('pm_token'));

  if (!token) {
    return <LoginPage onLogin={setToken} />;
  }

  const handleLogout = () => {
    localStorage.removeItem('pm_token');
    setToken(null);
  };

  return (
    <div className="flex h-screen">
      <aside className="w-56 border-r border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <h1 className="mb-6 text-lg font-bold">PandaMind</h1>
        <nav className="flex flex-col gap-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `rounded px-3 py-2 text-sm ${
                  isActive
                    ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                    : 'hover:bg-zinc-100 dark:hover:bg-zinc-800'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <button
          onClick={handleLogout}
          className="mt-auto block w-full rounded px-3 py-2 text-left text-xs text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          Log out
        </button>
      </aside>
      <main className="flex-1 overflow-auto p-6">
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/prompts" element={<PromptsPage />} />
        </Routes>
      </main>
    </div>
  );
}
