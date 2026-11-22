import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { Activity, ArrowRight, ShieldCheck } from 'lucide-react';
import { errorMessage, hasToken, login } from '../lib/api';
import { useApp } from '../state/AppContext';

export function Login() {
  const [email, setEmail] = useState('demo@serpscope.local');
  const [password, setPassword] = useState('demo1234');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const { refreshProjects } = useApp();

  if (hasToken()) return <Navigate to="/overview" replace />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      await login(email, password);
      await refreshProjects();
      navigate('/overview', { replace: true });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid min-h-screen bg-canvas lg:grid-cols-2">
      <div className="flex items-center justify-center px-6 py-12">
        <form onSubmit={submit} className="w-full max-w-md animate-fade-in">
          <div className="mb-8 flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br from-sky-400 to-violet-600 text-white shadow-glow"><Activity className="h-6 w-6" /></div>
            <div>
              <div className="text-lg font-bold tracking-tight text-white">SERPScope</div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-muted">Enterprise SEO intelligence</div>
            </div>
          </div>
          <div className="panel p-6">
            <h1 className="text-xl font-bold text-white">Sign in to your workspace</h1>
            <p className="mt-1.5 text-sm text-muted">Use the demo account to explore a deterministic synthetic dataset.</p>
            <div className="mt-6 space-y-4">
              <div>
                <label className="label" htmlFor="email">Email</label>
                <input id="email" className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required />
              </div>
              <div>
                <label className="label" htmlFor="password">Password</label>
                <input id="password" className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
              </div>
              {error ? <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">{error}</div> : null}
              <button className="btn btn-primary w-full py-2.5" disabled={loading} type="submit">{loading ? 'Signing in…' : 'Sign in'} <ArrowRight className="h-4 w-4" /></button>
            </div>
            <div className="mt-5 rounded-lg border border-accent/20 bg-accent/5 p-3 text-xs leading-5 text-muted">
              <div className="flex items-center gap-2 font-semibold text-accent"><ShieldCheck className="h-3.5 w-3.5" /> Demo credentials</div>
              <div className="mono mt-1.5">demo@serpscope.local / demo1234</div>
            </div>
          </div>
        </form>
      </div>
      <div className="relative hidden overflow-hidden border-l border-edge bg-gradient-to-br from-sky-950 via-panel to-violet-950 lg:flex lg:items-center lg:justify-center">
        <div className="absolute inset-0 opacity-30" style={{ backgroundImage: 'radial-gradient(circle at 20% 20%, #38bdf8 0, transparent 35%), radial-gradient(circle at 80% 70%, #8b5cf6 0, transparent 40%)' }} />
        <div className="relative max-w-lg px-12">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] uppercase tracking-widest text-slate-300">Evidence-first SEO operations</div>
          <h2 className="text-4xl font-bold leading-tight tracking-tight text-white">Every metric has a source. Every recommendation has a reason.</h2>
          <p className="mt-5 text-sm leading-7 text-slate-400">Crawl, diagnose, map, forecast and report across 23 enterprise SEO modules — with live jobs, transparent scoring and reviewable AI suggestions.</p>
          <div className="mt-8 grid grid-cols-3 gap-3">
            {[['23', 'Modules'], ['100k+', 'URL scale'], ['12', 'Interview scenarios']].map(([value, label]) => (
              <div key={label} className="rounded-xl border border-white/10 bg-white/5 p-4">
                <div className="text-xl font-bold text-white">{value}</div>
                <div className="mt-1 text-[11px] uppercase tracking-wider text-slate-400">{label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
