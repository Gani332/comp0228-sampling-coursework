import { useEffect, useState } from 'react';
import Simulator from './components/Simulator';
import Results from './components/Results';

type View = 'simulator' | 'results';
const current = (): View => (location.hash === '#results' ? 'results' : 'simulator');

export default function App() {
  const [view, setView] = useState<View>(current);
  useEffect(() => {
    const on = () => { setView(current()); window.scrollTo({ top: 0 }); };
    addEventListener('hashchange', on);
    return () => removeEventListener('hashchange', on);
  }, []);

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand"><span className="brand-mark" aria-hidden="true" />Optical Link <small>COMP0228</small></div>
          <nav className="tabs" aria-label="Views">
            <a href="#simulator" aria-current={view === 'simulator' ? 'page' : undefined}>Simulator</a>
            <a href="#results" aria-current={view === 'results' ? 'page' : undefined}>Results</a>
          </nav>
        </div>
      </header>
      <main className="shell">
        {view === 'simulator' ? <Simulator /> : <Results />}
      </main>
    </>
  );
}
