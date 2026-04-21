import { createRoot } from 'react-dom/client';
import App from './App';
import './styles/tokens.css';

if (import.meta.env.PROD) {
  window.addEventListener('keydown', (e) => {
    const reloadKey = e.key === 'F5';
    const ctrlReload = e.ctrlKey && (e.key === 'r' || e.key === 'R');
    const ctrlShiftReload = e.ctrlKey && e.shiftKey && (e.key === 'R' || e.key === 'F5');
    const devtools =
      e.key === 'F12' ||
      (e.ctrlKey && e.shiftKey && (e.key === 'I' || e.key === 'J' || e.key === 'C'));
    const viewSource = e.ctrlKey && (e.key === 'u' || e.key === 'U');
    const print = e.ctrlKey && (e.key === 'p' || e.key === 'P');
    if (reloadKey || ctrlReload || ctrlShiftReload || devtools || viewSource || print) {
      e.preventDefault();
      e.stopPropagation();
    }
  });
  window.addEventListener('contextmenu', (e) => e.preventDefault());
}

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('root element not found');
}
createRoot(rootElement).render(<App />);
