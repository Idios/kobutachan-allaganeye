// Variant B: "Neon Arena" — gaming/esports aesthetic
// High contrast, neon cyan/magenta, sharp angular UI, dense HUD feel.

const neonTheme = {
  name: 'Neon Arena',
  uiFont: '"Orbitron", "Rajdhani", "Russo One", sans-serif',
  bodyFont: '"Rajdhani", "Inter", sans-serif',
  monoFont: '"JetBrains Mono", "Consolas", monospace',
  bg: '#0b0d12',
  bgDeep: '#05060a',
  panel: '#121520',
  panelBorder: '1px solid #1f2436',
  cyan: '#00e5ff',
  magenta: '#ff2d92',
  yellow: '#ffe14a',
  green: '#3dff9a',
  text: '#d8dff0',
  textDim: '#6a7390',
  textBright: '#ffffff',
  danger: '#ff4060',
  chromeBg: '#05060a',
  chromeFg: '#d8dff0',
  chromeBorder: '1px solid #1f2436',
  switcherBg: 'rgba(18, 21, 32, 0.9)',
  switcherBorder: '1px solid #2a2f45',
  switcherActiveBg: '#00e5ff',
  switcherActiveFg: '#000',
  switcherFg: '#6a7390',
  thumbBg: 'linear-gradient(135deg, #1a1f30, #0a0c14)',
  thumbBorder: '1px solid rgba(0, 229, 255, 0.25)',
};

// Angular clipped box
const clipCorner = 'polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px)';

function NeonPanel({ children, style = {}, accent = neonTheme.cyan }) {
  return (
    <div style={{
      background: neonTheme.panel, clipPath: clipCorner,
      border: `1px solid ${accent}44`, position: 'relative', ...style,
    }}>
      {/* corner tick */}
      <div style={{ position: 'absolute', top: 0, right: 0, width: 14, height: 14,
        background: accent, clipPath: 'polygon(100% 0, 100% 100%, 0 0)', opacity: 0.6 }}/>
      {children}
    </div>
  );
}

// --- DROP ---
function NeonDrop({ theme }) {
  return (
    <div style={{flex: 1, padding: 24, display: 'flex', flexDirection: 'column', gap: 18, position: 'relative'}}>
      {/* Scan lines bg */}
      <div style={{position: 'absolute', inset: 0, pointerEvents: 'none', opacity: 0.5,
        background: 'repeating-linear-gradient(180deg, transparent 0, transparent 3px, rgba(0,229,255,0.02) 3px, rgba(0,229,255,0.02) 4px)'}}/>

      <div style={{display: 'flex', alignItems: 'center', gap: 14, zIndex: 2}}>
        <div style={{width: 4, height: 28, background: theme.cyan, boxShadow: `0 0 10px ${theme.cyan}`}}/>
        <div>
          <div style={{fontFamily: theme.uiFont, fontSize: 9, letterSpacing: 3, color: theme.magenta}}>READY</div>
          <div style={{fontFamily: theme.uiFont, fontSize: 20, fontWeight: 700, color: theme.textBright, letterSpacing: 1}}>SOURCE INPUT</div>
        </div>
        <div style={{flex: 1}}/>
        <div style={{fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim}}>SYS.01 › INGEST</div>
      </div>

      {/* Big drop zone */}
      <div style={{
        flex: 1, border: `2px dashed ${theme.cyan}`, background: `linear-gradient(180deg, rgba(0,229,255,0.05), transparent)`,
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        gap: 16, position: 'relative', clipPath: clipCorner, zIndex: 2,
      }}>
        {/* Plus cross icon */}
        <svg width="60" height="60" viewBox="0 0 60 60">
          <circle cx="30" cy="30" r="28" stroke={theme.cyan} strokeWidth="1" fill="none" opacity="0.5"/>
          <circle cx="30" cy="30" r="22" stroke={theme.cyan} strokeWidth="0.5" fill="none" opacity="0.3" strokeDasharray="2 2"/>
          <path d="M30 18 V42 M18 30 H42" stroke={theme.cyan} strokeWidth="2"/>
        </svg>
        <div style={{fontFamily: theme.uiFont, fontSize: 16, color: theme.cyan, letterSpacing: 4, fontWeight: 700}}>
          DROP FILE
        </div>
        <div style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim, letterSpacing: 1}}>
          .mp4 · .mkv · .avi · .mov
        </div>
        <button style={{
          marginTop: 8, padding: '8px 18px', background: 'transparent',
          border: `1px solid ${theme.magenta}`, color: theme.magenta,
          fontFamily: theme.uiFont, fontSize: 11, letterSpacing: 2, fontWeight: 600,
          clipPath: clipCorner, cursor: 'pointer',
        }}>BROWSE ▸</button>
      </div>

      {/* Recent bar */}
      <NeonPanel style={{padding: 10, zIndex: 2}} accent={theme.magenta}>
        <div style={{fontFamily: theme.uiFont, fontSize: 9, color: theme.magenta, letterSpacing: 3, marginBottom: 6, fontWeight: 600}}>RECENT ▸</div>
        <div style={{display: 'flex', gap: 8}}>
          {[
            { n: '04-08 21-14', d: '2:50:28', m: 9 },
            { n: '04-05 20-02', d: '1:45:12', m: 6 },
            { n: '03-28 19-45', d: '3:28:40', m: 11 },
          ].map((r, i) => (
            <div key={i} style={{
              flex: 1, padding: 8, background: theme.bgDeep,
              border: `1px solid ${theme.cyan}33`, fontFamily: theme.monoFont, fontSize: 9,
            }}>
              <div style={{color: theme.cyan, marginBottom: 2}}>▪ {r.n}</div>
              <div style={{color: theme.textDim}}>{r.d} · {r.m} matches</div>
            </div>
          ))}
        </div>
      </NeonPanel>
    </div>
  );
}

// --- DETECTING ---
function NeonDetecting({ theme }) {
  const phases = [
    { n: 'DETECTING', pct: 100, sub: '3410/3410', color: theme.green },
    { n: 'REFINING',  pct: 100, sub: '18/18',      color: theme.green },
    { n: 'SCOREBAR',  pct: 62,  sub: '9/15',       color: theme.cyan },
    { n: 'SPLITTING', pct: 0,   sub: '0/9',        color: theme.textDim },
  ];
  return (
    <div style={{flex: 1, padding: 20, display: 'flex', flexDirection: 'column', gap: 14, position: 'relative'}}>
      {/* scan lines */}
      <div style={{position: 'absolute', inset: 0, pointerEvents: 'none',
        background: 'repeating-linear-gradient(180deg, transparent 0, transparent 3px, rgba(0,229,255,0.03) 3px, rgba(0,229,255,0.03) 4px)'}}/>

      {/* top header */}
      <div style={{display: 'flex', alignItems: 'center', gap: 14, zIndex: 2}}>
        <div style={{position: 'relative', width: 60, height: 60}}>
          <div style={{position: 'absolute', inset: 0, border: `2px solid ${theme.cyan}`, borderTopColor: 'transparent', borderRadius: '50%',
            animation: 'spin-cw 1.2s linear infinite'}}/>
          <div style={{position: 'absolute', inset: 8, border: `1px solid ${theme.magenta}`, borderBottomColor: 'transparent', borderRadius: '50%',
            animation: 'spin-ccw 2s linear infinite'}}/>
          <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: theme.uiFont, fontSize: 14, color: theme.cyan, fontWeight: 700}}>62</div>
        </div>
        <div style={{flex: 1}}>
          <div style={{fontFamily: theme.uiFont, fontSize: 9, color: theme.magenta, letterSpacing: 3, fontWeight: 600}}>PROCESS ACTIVE</div>
          <div style={{fontFamily: theme.uiFont, fontSize: 15, color: theme.textBright, marginTop: 2, letterSpacing: 1}}>2026-04-08 21-14-05.mkv</div>
          <div style={{fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim, marginTop: 3}}>
            2:50:28 · 1920×1080@60 · h264 · <span style={{color: theme.green}}>GPU</span>
          </div>
        </div>
        <div style={{textAlign: 'right'}}>
          <div style={{fontFamily: theme.uiFont, fontSize: 9, color: theme.textDim, letterSpacing: 2}}>ETA</div>
          <div style={{fontFamily: theme.uiFont, fontSize: 22, color: theme.yellow, fontWeight: 700, textShadow: `0 0 8px ${theme.yellow}66`}}>4:12</div>
        </div>
      </div>

      {/* 4 phase bars */}
      <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, zIndex: 2}}>
        {phases.map((p, i) => (
          <NeonPanel key={i} style={{padding: 10}} accent={p.color}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6}}>
              <span style={{fontFamily: theme.uiFont, fontSize: 11, color: p.color, letterSpacing: 2, fontWeight: 700}}>{p.n}</span>
              <span style={{fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim}}>{p.sub}</span>
            </div>
            <div style={{height: 6, background: theme.bgDeep, position: 'relative', overflow: 'hidden'}}>
              <div style={{position: 'absolute', inset: 0, width: `${p.pct}%`, background: p.color,
                boxShadow: p.pct > 0 && p.pct < 100 ? `0 0 10px ${p.color}` : 'none'}}/>
              {/* animated stripe */}
              {p.pct > 0 && p.pct < 100 && (
                <div style={{position: 'absolute', inset: 0, width: `${p.pct}%`,
                  background: 'repeating-linear-gradient(90deg, transparent 0 8px, rgba(255,255,255,0.3) 8px 10px)',
                  animation: 'stripe-flow 1s linear infinite'}}/>
              )}
            </div>
            <div style={{marginTop: 6, fontFamily: theme.uiFont, fontSize: 18, color: theme.textBright, fontWeight: 700}}>
              {p.pct}<span style={{fontSize: 11, color: theme.textDim}}>%</span>
            </div>
          </NeonPanel>
        ))}
      </div>

      {/* Live log */}
      <NeonPanel style={{flex: 1, padding: 10, zIndex: 2, minHeight: 0}} accent={theme.cyan}>
        <div style={{display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6}}>
          <div style={{width: 6, height: 6, background: theme.green, boxShadow: `0 0 6px ${theme.green}`,
            animation: 'pulse-dot 1s ease-in-out infinite alternate'}}/>
          <span style={{fontFamily: theme.uiFont, fontSize: 10, color: theme.cyan, letterSpacing: 2, fontWeight: 600}}>LIVE TELEMETRY</span>
        </div>
        <div style={{fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim, lineHeight: 1.7}}>
          <div><span style={{color: theme.green}}>[07:01.2]</span> scorebar.probe r=9/15 ROI=35-65%×0-4% σ=58.2 → <span style={{color: theme.green}}>MATCH_BOUNDARY</span></div>
          <div><span style={{color: theme.green}}>[07:01.4]</span> scorebar.probe r=10/15 σ=12.4 → <span style={{color: theme.danger}}>NON_FL</span></div>
          <div><span style={{color: theme.green}}>[07:01.7]</span> scorebar.probe r=11/15 σ=61.8 → <span style={{color: theme.green}}>MATCH_BOUNDARY</span></div>
          <div><span style={{color: theme.cyan}}>[07:01.9]</span> gpu.decode chunk=8/16 fps=512.3 util=74%</div>
          <div><span style={{color: theme.yellow}}>[07:02.1]</span> workers=16 threads=32 mem=4.2GB/61.6GB</div>
        </div>
      </NeonPanel>

      <style>{`
        @keyframes spin-cw { to { transform: rotate(360deg); } }
        @keyframes spin-ccw { to { transform: rotate(-360deg); } }
        @keyframes stripe-flow { to { background-position: 20px 0; } }
        @keyframes pulse-dot { to { opacity: 0.3; } }
      `}</style>
    </div>
  );
}

// --- COMPLETE ---
function NeonComplete({ theme }) {
  const meta = window.AE_META;
  const samples = window.AE_BRIGHTNESS;
  const [selected, setSelected] = useState(4);
  const match = meta.matches[selected - 1];
  const W = 700, H = 90;
  const path = buildBrightnessPath(samples, W, H);

  return (
    <div style={{flex: 1, padding: 16, display: 'flex', flexDirection: 'column', gap: 12, position: 'relative'}}>
      <div style={{position: 'absolute', inset: 0, pointerEvents: 'none', opacity: 0.4,
        background: 'repeating-linear-gradient(180deg, transparent 0, transparent 3px, rgba(0,229,255,0.02) 3px, rgba(0,229,255,0.02) 4px)'}}/>

      {/* Top stats row */}
      <div style={{display: 'flex', gap: 10, zIndex: 2}}>
        <NeonPanel style={{flex: 1, padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10}} accent={theme.green}>
          <div style={{width: 8, height: 8, background: theme.green, boxShadow: `0 0 8px ${theme.green}`}}/>
          <div style={{flex: 1}}>
            <div style={{fontFamily: theme.uiFont, fontSize: 9, color: theme.green, letterSpacing: 2, fontWeight: 600}}>COMPLETE</div>
            <div style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.text}}>2026-04-08 21-14-05.mkv</div>
          </div>
          <div style={{fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim}}>07:58 elapsed</div>
        </NeonPanel>
        {[
          { l: 'MATCHES', v: meta.matches.length, c: theme.cyan },
          { l: 'FL_MATCH', v: meta.matches.filter(m=>m.type==='fl_match').length, c: theme.magenta },
          { l: 'DURATION', v: meta.source_duration_display, c: theme.yellow },
        ].map((s, i) => (
          <NeonPanel key={i} style={{padding: '6px 14px', minWidth: 90}} accent={s.c}>
            <div style={{fontFamily: theme.uiFont, fontSize: 9, color: s.c, letterSpacing: 2, fontWeight: 600}}>{s.l}</div>
            <div style={{fontFamily: theme.uiFont, fontSize: 18, color: theme.textBright, fontWeight: 700}}>{s.v}</div>
          </NeonPanel>
        ))}
      </div>

      {/* Timeline */}
      <NeonPanel style={{padding: 12, zIndex: 2}} accent={theme.cyan}>
        <div style={{display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8}}>
          <span style={{fontFamily: theme.uiFont, fontSize: 10, color: theme.cyan, letterSpacing: 3, fontWeight: 600}}>TIMELINE ▸ BRIGHTNESS</span>
          <span style={{fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim}}>threshold=15</span>
          <div style={{flex: 1}}/>
          <div style={{display:'flex', gap: 10, fontFamily: theme.monoFont, fontSize: 9}}>
            <span><span style={{display:'inline-block', width: 10, height: 3, background: theme.magenta, verticalAlign: 'middle', marginRight: 4}}/>blackout</span>
            <span><span style={{display:'inline-block', width: 10, height: 3, background: theme.cyan, verticalAlign: 'middle', marginRight: 4}}/>fl_match</span>
            <span><span style={{display:'inline-block', width: 10, height: 3, background: theme.textDim, verticalAlign: 'middle', marginRight: 4}}/>unknown</span>
          </div>
        </div>
        <svg viewBox={`0 0 ${W} ${H + 42}`} style={{width: '100%', height: 'auto', display: 'block'}} preserveAspectRatio="none">
          {/* blackout fill */}
          {findBlackoutRegions(samples, meta.source_duration, 15).map((r, i) => {
            const x1 = (r.start / meta.source_duration) * W;
            const x2 = (r.end / meta.source_duration) * W;
            return <rect key={i} x={x1} y={0} width={Math.max(1.5, x2-x1)} height={H} fill={theme.magenta} fillOpacity="0.2"/>;
          })}
          <line x1={0} x2={W} y1={H - (15/255)*H} y2={H - (15/255)*H} stroke={theme.magenta} strokeOpacity="0.5" strokeDasharray="2 2" strokeWidth="0.5"/>

          <path d={path + ` L ${W} ${H} L 0 ${H} Z`} fill={theme.cyan} fillOpacity="0.1"/>
          <path d={path} stroke={theme.cyan} strokeWidth="1" fill="none" style={{filter: `drop-shadow(0 0 2px ${theme.cyan})`}}/>

          {/* matches */}
          {meta.matches.map((m, i) => {
            const x1 = (m.start_time / meta.source_duration) * W;
            const x2 = (m.end_time / meta.source_duration) * W;
            const isSel = m.index === selected;
            const fill = m.type === 'fl_match' ? theme.cyan : theme.textDim;
            return (
              <g key={i} onClick={() => setSelected(m.index)} style={{cursor: 'pointer'}}>
                <rect x={x1} y={H + 4} width={Math.max(2, x2-x1)} height={16}
                  fill={fill} fillOpacity={isSel ? 1 : 0.6}
                  stroke={isSel ? theme.yellow : 'none'} strokeWidth={isSel ? 1.5 : 0}
                  style={{filter: isSel ? `drop-shadow(0 0 3px ${theme.yellow})` : 'none'}}/>
                <text x={x1 + 2} y={H + 15} fontSize="7" fill={theme.bg} fontFamily={theme.monoFont} fontWeight="700">
                  {String(m.index).padStart(2, '0')}
                </text>
              </g>
            );
          })}

          {[0, 0.25, 0.5, 0.75, 1].map(p => (
            <text key={p} x={p*W} y={H + 36} fontSize="7" fill={theme.textDim} fontFamily={theme.monoFont}
              textAnchor={p === 0 ? 'start' : p === 1 ? 'end' : 'middle'}>{fmtTime(p * meta.source_duration)}</text>
          ))}
        </svg>
      </NeonPanel>

      {/* Match list + preview */}
      <div style={{flex: 1, display: 'flex', gap: 10, minHeight: 0, zIndex: 2}}>
        <NeonPanel style={{flex: 1, padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column'}} accent={theme.cyan}>
          <div style={{padding: '8px 12px', borderBottom: `1px solid ${theme.cyan}33`, display: 'flex', alignItems: 'center', gap: 8}}>
            <span style={{fontFamily: theme.uiFont, fontSize: 10, color: theme.cyan, letterSpacing: 2, fontWeight: 600}}>▸ MATCHES</span>
            <span style={{fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim}}>{meta.matches.length} items</span>
          </div>
          <div style={{flex: 1, overflow: 'auto'}}>
            {meta.matches.map((m) => {
              const isSel = m.index === selected;
              return (
                <div key={m.index} onClick={() => setSelected(m.index)} style={{
                  display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px',
                  cursor: 'pointer',
                  background: isSel ? `linear-gradient(90deg, ${theme.cyan}22, transparent)` : 'transparent',
                  borderLeft: isSel ? `3px solid ${theme.yellow}` : '3px solid transparent',
                }}>
                  <div style={{fontFamily: theme.uiFont, fontSize: 14, color: isSel ? theme.yellow : theme.cyan, fontWeight: 700, width: 26}}>
                    {String(m.index).padStart(2, '0')}
                  </div>
                  <MatchThumb index={m.index} theme={theme} w={44} h={25} />
                  <div style={{flex: 1}}>
                    <div style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.text}}>{m.start_display} → {m.end_display}</div>
                    <div style={{fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim}}>{m.duration_display}</div>
                  </div>
                  <div style={{
                    fontFamily: theme.uiFont, fontSize: 8, padding: '1px 6px', letterSpacing: 1.5,
                    color: m.type === 'fl_match' ? theme.cyan : theme.textDim,
                    border: `1px solid ${m.type === 'fl_match' ? theme.cyan : theme.textDim}66`,
                    fontWeight: 600,
                  }}>{m.type === 'fl_match' ? 'FL' : 'UNK'}</div>
                </div>
              );
            })}
          </div>
        </NeonPanel>

        <div style={{width: 260, display: 'flex', flexDirection: 'column', gap: 10}}>
          <div style={{aspectRatio: '16/9', background: '#000', position: 'relative', overflow: 'hidden',
            border: `1px solid ${theme.magenta}`, clipPath: clipCorner}}>
            <MatchThumb index={match.index} theme={theme} w="100%" h="100%" />
            <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
              <div style={{width: 40, height: 40, background: theme.magenta, clipPath: 'polygon(0 0, 100% 50%, 0 100%)',
                boxShadow: `0 0 20px ${theme.magenta}`}}/>
            </div>
            <div style={{position: 'absolute', top: 6, left: 6, padding: '2px 6px', background: theme.magenta,
              fontFamily: theme.uiFont, fontSize: 9, color: '#000', fontWeight: 700, letterSpacing: 1}}>
              MATCH {String(match.index).padStart(3, '0')}
            </div>
            <div style={{position: 'absolute', bottom: 4, right: 6, fontFamily: theme.monoFont, fontSize: 10, color: theme.yellow, textShadow: '0 0 4px black'}}>
              {match.duration_display}
            </div>
          </div>

          <NeonPanel style={{padding: 10}} accent={theme.cyan}>
            <div style={{fontFamily: theme.monoFont, fontSize: 10, lineHeight: 1.8, color: theme.text}}>
              <div style={{color: theme.cyan, fontSize: 11, marginBottom: 4, fontFamily: theme.uiFont, letterSpacing: 1.5, fontWeight: 600}}>
                match_{String(match.index).padStart(3, '0')}.mp4
              </div>
              <div style={{display:'grid', gridTemplateColumns:'auto 1fr', gap:'2px 10px'}}>
                <span style={{color: theme.textDim}}>START</span><span>{match.start_display}</span>
                <span style={{color: theme.textDim}}>END</span><span>{match.end_display}</span>
                <span style={{color: theme.textDim}}>LEN</span><span>{match.duration_display}</span>
                <span style={{color: theme.textDim}}>TYPE</span><span style={{color: match.type === 'fl_match' ? theme.cyan : theme.textDim}}>{match.type.toUpperCase()}</span>
              </div>
            </div>
          </NeonPanel>

          <button style={{
            padding: '10px', background: theme.magenta, border: 'none',
            fontFamily: theme.uiFont, fontSize: 11, color: '#000', letterSpacing: 3, fontWeight: 700,
            clipPath: clipCorner, cursor: 'pointer', marginTop: 'auto',
          }}>▸ OPEN OUTPUT</button>
        </div>
      </div>
    </div>
  );
}

function NeonApp({ state, setState }) {
  const theme = neonTheme;
  return (
    <div style={{width:'100%', height:'100%', background: theme.bg, color: theme.text,
      display: 'flex', flexDirection: 'column', position: 'relative', overflow: 'hidden'}}>
      <StateSwitcher state={state} setState={setState} theme={theme} />
      <WindowChrome title="ALLAGAN_EYE ▸ v0.1.1" theme={theme} />

      <div style={{flex: 1, display: 'flex', minHeight: 0}}>
        <div style={{width: 44, background: theme.bgDeep, borderRight: `1px solid ${theme.cyan}22`,
          display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '12px 0', gap: 12}}>
          <div style={{width: 24, height: 24, background: theme.cyan, clipPath: 'polygon(50% 0, 100% 100%, 0 100%)'}}/>
          {['▸', '◈', '⚙', '?'].map((c, i) => (
            <div key={i} style={{width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: theme.uiFont, fontSize: 13, color: i === 0 ? theme.cyan : theme.textDim,
              border: i === 0 ? `1px solid ${theme.cyan}` : '1px solid transparent',
              background: i === 0 ? `${theme.cyan}22` : 'transparent'}}>{c}</div>
          ))}
        </div>
        <div style={{flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0}}>
          {state === 'drop' && <NeonDrop theme={theme} />}
          {state === 'detecting' && <NeonDetecting theme={theme} />}
          {state === 'complete' && <NeonComplete theme={theme} />}
        </div>
      </div>
    </div>
  );
}

window.NeonApp = NeonApp;
window.neonTheme = neonTheme;
