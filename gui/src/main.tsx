import { createRoot } from 'react-dom/client';
import App from './App';
import { installBrowserShortcutSuppressor } from './lib/preventBrowserShortcuts';
import './styles/tokens.css';

if (import.meta.env.PROD) {
  installBrowserShortcutSuppressor();
}

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('root element not found');
}
createRoot(rootElement).render(<App />);
