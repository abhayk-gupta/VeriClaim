import { Outlet, Link } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { LogOut, Sun, Moon, LayoutDashboard } from 'lucide-react';
import { useState, useEffect } from 'react';

export default function DashboardLayout() {
  const { user, logout } = useAuth();
  const [theme, setTheme] = useState(localStorage.getItem('theme') || 'light');

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => setTheme(t => t === 'light' ? 'dark' : 'light');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <header style={{ 
        height: '64px', 
        borderBottom: '1px solid var(--border-color)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 1.5rem',
        backgroundColor: 'var(--surface-color)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', fontWeight: 'bold' }}>
          <LayoutDashboard className="text-primary" />
          <Link to="/" style={{ color: 'var(--text-primary)', textDecoration: 'none', fontSize: '1.25rem' }}>
            VeriClaim
          </Link>
        </div>
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
            {user?.full_name}
          </span>
          <button onClick={toggleTheme} className="btn btn-outline" style={{ padding: '0.5rem' }}>
            {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
          </button>
          <button onClick={logout} className="btn btn-outline" style={{ padding: '0.5rem' }}>
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <main style={{ flex: 1, overflow: 'hidden' }}>
        <Outlet />
      </main>
    </div>
  );
}
