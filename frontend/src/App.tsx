import type { ReactNode } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { hasToken } from './lib/api';
import { CaseStudyDetail, CaseStudies } from './pages/CaseStudies';
import { Landing } from './pages/Landing';
import { Login } from './pages/Login';
import { ModulePage } from './pages/ModulePage';

function Protected({ children }: { children: ReactNode }) {
  if (!hasToken()) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/case-studies" element={<CaseStudies />} />
      <Route path="/case-studies/:projectId" element={<CaseStudyDetail />} />
      <Route path="/login" element={<Login />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route path="/:moduleId" element={<ModulePage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
