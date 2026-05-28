import React from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { LayoutDashboard, ShieldAlert, LogOut, Menu, Clock, History } from 'lucide-react';
import './Layout.css';

export const Layout: React.FC = () => {
  const navigate = useNavigate();
  const [isSidebarOpen, setIsSidebarOpen] = React.useState(false);
  const [pendingCount, setPendingCount] = React.useState(0);

  React.useEffect(() => {
    const fetchCount = async () => {
      try {
        const res = await fetch('http://localhost:3000/sessions/scheduled-syncs?status=PENDING', {
          credentials: 'include',
        });
        if (res.status === 401) {
          localStorage.removeItem('user');
          window.location.href = '/login';
          return;
        }
        if (res.ok) {
          const data = await res.json();
          setPendingCount(Array.isArray(data) ? data.length : 0);
        }
      } catch {
        // silencioso
      }
    };
    fetchCount();
    const interval = setInterval(fetchCount, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleLogout = async () => {
    try {
      await fetch('http://localhost:3000/auth/logout', {
        method: 'POST',
        credentials: 'include',
      });
    } catch {
      // silencioso
    }
    localStorage.removeItem('user');
    navigate('/login');
  };

  const toggleSidebar = () => {
    setIsSidebarOpen(!isSidebarOpen);
  };

  return (
    <div className="layout-container">
      {/* Mobile toggle button */}
      <button className="mobile-toggle" onClick={toggleSidebar}>
        <Menu size={24} />
      </button>

      {/* Sidebar */}
      <aside className={`sidebar ${isSidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <div className="logo-container">
            <h2>VELOX</h2>
          </div>
        </div>

        <nav className="sidebar-nav">
          <NavLink
            to="/dashboard"
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            onClick={() => setIsSidebarOpen(false)}
          >
            <LayoutDashboard size={20} />
            <span>Dashboard</span>
          </NavLink>

          <NavLink
            to="/auditoria"
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            onClick={() => setIsSidebarOpen(false)}
          >
            <ShieldAlert size={20} />
            <span>Auditoria</span>
          </NavLink>

          <NavLink
            to="/fichas"
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            onClick={() => setIsSidebarOpen(false)}
          >
            <History size={20} />
            <span>Fichas</span>
          </NavLink>

          <NavLink
            to="/tarefas-pendentes"
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            onClick={() => setIsSidebarOpen(false)}
          >
            <Clock size={20} />
            <span>Tarefas Pendentes</span>
            {pendingCount > 0 && (
              <span className="nav-badge">{pendingCount}</span>
            )}
          </NavLink>
        </nav>

        <div className="sidebar-footer">
          <button className="logout-btn" onClick={handleLogout}>
            <LogOut size={20} />
            <span>Sair</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <Outlet />
      </main>

      {/* Overlay for mobile */}
      {isSidebarOpen && (
        <div className="sidebar-overlay" onClick={() => setIsSidebarOpen(false)} />
      )}
    </div>
  );
};
