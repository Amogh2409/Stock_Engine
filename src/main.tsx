import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import {ErrorBoundary} from './components/ErrorBoundary';
import {SAVED_RUN_KEY} from './utils/screenerEngine';
import './index.css';

// The boundary sits outside App so a failure in App's own render is caught too.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary
      onReset={() => {
        try {
          localStorage.removeItem(SAVED_RUN_KEY);
        } catch {
          // Storage may be unavailable; there is then nothing to clear.
        }
      }}
    >
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
