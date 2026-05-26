import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { Audit } from './pages/Audit';
import { PendingTasks } from './pages/PendingTasks';
import { History } from './pages/History';
import { Layout } from './components/Layout';
import './App.css';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />

        <Route element={<Layout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/auditoria" element={<Audit />} />
          <Route path="/tarefas-pendentes" element={<PendingTasks />} />
          <Route path="/fichas" element={<History />} />
        </Route>

        <Route path="*" element={<Navigate to="/login" />} />
      </Routes>
    </Router>
  );
}

export default App;
