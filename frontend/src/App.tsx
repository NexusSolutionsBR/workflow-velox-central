import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { Audit } from './pages/Audit';
import { PendingTasks } from './pages/PendingTasks';
import { History } from './pages/History';
import { Layout } from './components/Layout';
import './App.css';

const isAdmin = (): boolean => {
  try {
    const raw = localStorage.getItem('user');
    return raw ? JSON.parse(raw).role === 'ADMIN' : false;
  } catch {
    return false;
  }
};

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />

        <Route element={<Layout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/auditoria" element={isAdmin() ? <Audit /> : <Navigate to="/dashboard" />} />
          <Route path="/tarefas-pendentes" element={<PendingTasks />} />
          <Route path="/fichas" element={<History />} />
        </Route>

        <Route path="*" element={<Navigate to="/login" />} />
      </Routes>
    </Router>
  );
}

export default App;
