import { createRoot } from 'react-dom/client';
import App from './App';
import { installBrowserShortcutSuppressor } from './lib/preventBrowserShortcuts';
import './styles/tokens.css';
import './styles/a11y.css';

if (import.meta.env.PROD) {
  installBrowserShortcutSuppressor();
}

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('root element not found');
}
createRoot(rootElement).render(<App />);
