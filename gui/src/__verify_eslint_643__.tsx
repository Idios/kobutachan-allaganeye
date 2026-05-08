// gui/src/__verify_eslint_643__.tsx
//
// This file is intentionally invalid for ESLint verification of #643.
// It MUST be deleted (along with the verification PR being closed without
// merge) once CI fail evidence is captured. Do not merge this file into
// any long-lived branch.

export function _verify643(): void {
  // Bare global calls (no-restricted-globals)
  confirm('bare global confirm');
  alert('bare global alert');
  prompt('bare global prompt');

  // window.X member access (no-restricted-properties)
  window.confirm('member access confirm');
  window.alert('member access alert');
  window.prompt('member access prompt');
}
