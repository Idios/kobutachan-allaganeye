import { createRoot } from 'react-dom/client';
import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ErrorModal } from './components/ErrorModal';
import { installGlobalErrorListener } from './lib/globalErrorListener';
import { installBrowserShortcutSuppressor } from './lib/preventBrowserShortcuts';
import './styles/tokens.css';
import './styles/a11y.css';

if (import.meta.env.PROD) {
  installBrowserShortcutSuppressor();
}

// #614: install JS error / unhandledrejection / Tauri panic listeners
// before React mounts so any error during initial render is captured.
installGlobalErrorListener();

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('root element not found');
}
createRoot(rootElement).render(
  <>
    {/* #614 ErrorBoundary catches React-internal exceptions. ErrorModal
        lives outside it so it remains visible after the boundary blanks
        out the broken sub-tree. */}
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
    <ErrorModal />
  </>,
);
