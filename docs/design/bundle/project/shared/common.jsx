// Shared helpers for all Allagan Eye variants

const { useState, useEffect, useRef, useMemo } = React;

// Format seconds as H:MM:SS or MM:SS
function fmtTime(s) {
  s = Math.max(0, Math.floor(s));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

// The 3 flow states
const STATES = ['drop', 'detecting', 'complete'];

// State dot UI — for state-switcher tabs in each artboard
function StateSwitcher({ state, setState, theme }) {
  const labels = { drop: 'インポート', detecting: '検知中', complete: '完了' };
  return (
    <div style={{
      position: 'absolute', top: 8, right: 8, zIndex: 50,
      display: 'flex', gap: 4, padding: 4,
      background: theme.switcherBg || 'rgba(0,0,0,0.4)',
      border: theme.switcherBorder || '1px solid rgba(255,255,255,0.1)',
      borderRadius: 20, backdropFilter: 'blur(8px)',
      fontFamily: theme.uiFont,
    }}>
      {STATES.map(s => (
        <button
          key={s}
          onClick={() => setState(s)}
          style={{
            padding: '4px 10px', fontSize: 10, fontWeight: 600,
            letterSpacing: 0.4, textTransform: 'uppercase',
            border: 'none', borderRadius: 14, cursor: 'pointer',
            background: state === s ? (theme.switcherActiveBg || '#fff') : 'transparent',
            color: state === s ? (theme.switcherActiveFg || '#000') : (theme.switcherFg || '#aaa'),
            transition: 'all 0.15s',
          }}
        >{labels[s]}</button>
      ))}
    </div>
  );
}

// Window chrome (traffic lights) — for Electron look
function WindowChrome({ title, theme }) {
  return (
    <div style={{
      height: 32, display: 'flex', alignItems: 'center',
      padding: '0 12px', gap: 8,
      background: theme.chromeBg, color: theme.chromeFg,
      borderBottom: theme.chromeBorder,
      fontFamily: theme.uiFont, fontSize: 11, letterSpacing: 0.3,
      userSelect: 'none', WebkitAppRegion: 'drag',
    }}>
      <div style={{display: 'flex', gap: 6}}>
        <div style={{width: 11, height: 11, borderRadius: '50%', background: '#ff5f57'}} />
        <div style={{width: 11, height: 11, borderRadius: '50%', background: '#febc2e'}} />
        <div style={{width: 11, height: 11, borderRadius: '50%', background: '#28c840'}} />
      </div>
      <div style={{flex: 1, textAlign: 'center', opacity: 0.7}}>{title}</div>
      <div style={{width: 52}} />
    </div>
  );
}

// Brightness path (SVG polyline) generator
function buildBrightnessPath(samples, width, height, yScale = 1) {
  const n = samples.length;
  let d = '';
  for (let i = 0; i < n; i++) {
    const x = (i / (n - 1)) * width;
    const y = height - (samples[i] / 255) * height * yScale;
    d += (i === 0 ? 'M' : 'L') + x.toFixed(2) + ' ' + y.toFixed(2) + ' ';
  }
  return d;
}

// Find blackout regions in brightness samples (threshold-based)
function findBlackoutRegions(samples, duration, threshold = 15) {
  const regions = [];
  let start = null;
  for (let i = 0; i < samples.length; i++) {
    const t = (i / (samples.length - 1)) * duration;
    if (samples[i] < threshold) {
      if (start === null) start = t;
    } else {
      if (start !== null) { regions.push({ start, end: t }); start = null; }
    }
  }
  if (start !== null) regions.push({ start, end: duration });
  return regions;
}

// Placeholder thumbnail for a match — abstract shimmer based on index
function MatchThumb({ index, theme, w = 96, h = 54 }) {
  const hue = (index * 47) % 360;
  return (
    <div style={{
      width: w, height: h, borderRadius: 2,
      background: theme.thumbBg || `linear-gradient(135deg, oklch(0.25 0.08 ${hue}), oklch(0.15 0.05 ${hue + 60}))`,
      position: 'relative', overflow: 'hidden', flexShrink: 0,
      border: theme.thumbBorder || '1px solid rgba(255,255,255,0.08)',
    }}>
      {/* faux HUD elements */}
      <div style={{ position:'absolute', top:4, left:4, width: 16, height: 3, background:'rgba(255,255,255,0.4)' }} />
      <div style={{ position:'absolute', top:4, right:4, width: 12, height: 12, border:'1px solid rgba(255,255,255,0.3)', borderRadius:'50%' }} />
      <div style={{ position:'absolute', bottom: 4, left: '50%', transform:'translateX(-50%)', display:'flex', gap: 1 }}>
        {[0,1,2,3,4].map(i => <div key={i} style={{width: 6, height: 6, background:'rgba(255,255,255,0.2)'}} />)}
      </div>
      <div style={{
        position:'absolute', inset:0,
        background: `radial-gradient(circle at ${30+(index*13)%40}% ${40+(index*7)%20}%, rgba(255,220,100,0.35), transparent 40%)`,
      }} />
    </div>
  );
}

Object.assign(window, {
  fmtTime, STATES, StateSwitcher, WindowChrome,
  buildBrightnessPath, findBlackoutRegions, MatchThumb,
});
