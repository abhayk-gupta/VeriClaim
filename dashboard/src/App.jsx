import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import DashboardLayout from './layouts/DashboardLayout';
import LoginPage from './pages/LoginPage';
import ClaimQueuePage from './pages/ClaimQueuePage';
import ClaimDetailPage from './pages/ClaimDetailPage';
import { useAuth } from './hooks/useAuth';

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  
  if (loading) return <div>Loading...</div>;
  if (!user) return <Navigate to="/login" replace />;
  
  return children;
}

function App() {
  return (
    <BrowserRouter basename="/dashboard">
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={
          <ProtectedRoute>
            <DashboardLayout />
          </ProtectedRoute>
        }>
          <Route index element={<ClaimQueuePage />} />
          <Route path="claims" element={<ClaimQueuePage />} />
          <Route path="claims/:id" element={<ClaimDetailPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
