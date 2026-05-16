// Variant A: "Aetheric Observatory" — FF14/Allagan aesthetic
// Gold/cyan/black palette, geometric flourishes, slightly ceremonial.

const aetherTheme = {
  name: 'Aetheric Observatory',
  uiFont: '"Cinzel", "Trajan Pro", "Cormorant Garamond", serif',
  bodyFont: '"Inter", "Segoe UI", sans-serif',
  monoFont: '"JetBrains Mono", "Consolas", monospace',
  bg: '#0a0e14',
  bgDeep: '#05070b',
  panel: 'linear-gradient(180deg, #0f1420 0%, #0a0e14 100%)',
  panelBorder: '1px solid rgba(200, 163, 92, 0.18)',
  gold: '#c8a35c',
  goldBright: '#e8c47a',
  goldDim: '#8a7040',
  cyan: '#4ac3d9',
  cyanBright: '#7ee0f0',
  blue: '#2b6e99',
  text: '#d8cfbb',
  textDim: '#8a8270',
  textBright: '#f0e8d4',
  danger: '#c87058',
  chromeBg: 'linear-gradient(180deg, #0a0e14, #050709)',
  chromeFg: '#c8a35c',
  chromeBorder: '1px solid rgba(200, 163, 92, 0.15)',
  switcherBg: 'rgba(10, 14, 20, 0.8)',
  switcherBorder: '1px solid rgba(200, 163, 92, 0.25)',
  switcherActiveBg: 'linear-gradient(180deg, #c8a35c, #8a7040)',
  switcherActiveFg: '#0a0e14',
  switcherFg: '#8a8270',
  thumbBg: 'linear-gradient(135deg, #1a2230, #0a0e14)',
  thumbBorder: '1px solid rgba(200, 163, 92, 0.2)',
};

// Allagan geometric corner ornament
function AllaganCorner({ size = 20, color = '#c8a35c', style = {} }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" style={style}>
      <path d="M0 0 H10 M0 0 V10 M2 2 L7 2 L7 7 L2 7 Z" stroke={color} strokeWidth="0.8" fill="none" opacity="0.8"/>
      <circle cx="10" cy="10" r="1.5" fill={color} opacity="0.4"/>
    </svg>
  );
}

// Allagan frame wrapper
function AllaganFrame({ children, style = {}, corners = true }) {
  return (
    <div style={{ position: 'relative', ...style }}>
      {corners && <>
        <AllaganCorner style={{ position: 'absolute', top: 0, left: 0 }} />
        <AllaganCorner style={{ position: 'absolute', top: 0, right: 0, transform: 'rotate(90deg)' }} />
        <AllaganCorner style={{ position: 'absolute', bottom: 0, left: 0, transform: 'rotate(-90deg)' }} />
        <AllaganCorner style={{ position: 'absolute', bottom: 0, right: 0, transform: 'rotate(180deg)' }} />
      </>}
      {children}
    </div>
  );
}

// Rotating Allagan wheel / sigil (used in detecting state)
function AllaganSigil({ size = 120, rotating = true }) {
  const ring = (r, segs, thickness = 0.4) => {
    const els = [];
    for (let i = 0; i < segs; i++) {
      const a1 = (i / segs) * Math.PI * 2;
      const a2 = ((i + 0.7) / segs) * Math.PI * 2;
      const x1 = 60 + Math.cos(a1) * r, y1 = 60 + Math.sin(a1) * r;
      const x2 = 60 + Math.cos(a2) * r, y2 = 60 + Math.sin(a2) * r;
      els.push(<path key={i} d={`M${x1} ${y1} A${r} ${r} 0 0 1 ${x2} ${y2}`} stroke="#c8a35c" strokeWidth={thickness} fill="none" />);
    }
    return els;
  };
  return (
    <div style={{ width: size, height: size, position: 'relative' }}>
      <style>{`@keyframes spin-cw { to { transform: rotate(360deg); } } @keyframes spin-ccw { to { transform: rotate(-360deg); } }`}</style>
      <svg viewBox="0 0 120 120" width={size} height={size} style={{ position:'absolute', animation: rotating ? 'spin-cw 24s linear infinite' : 'none' }}>
        {ring(55, 24, 0.5)}
        {ring(45, 12, 0.8)}
      </svg>
      <svg viewBox="0 0 120 120" width={size} height={size} style={{ position:'absolute', animation: rotating ? 'spin-ccw 16s linear infinite' : 'none' }}>
        {ring(35, 6, 1)}
        <polygon points="60,30 85,75 35,75" stroke="#c8a35c" strokeWidth="0.8" fill="none" opacity="0.7"/>
        <polygon points="60,90 35,45 85,45" stroke="#4ac3d9" strokeWidth="0.6" fill="none" opacity="0.6"/>
      </svg>
      <svg viewBox="0 0 120 120" width={size} height={size} style={{ position:'absolute', animation: rotating ? 'spin-cw 10s linear infinite' : 'none' }}>
        <circle cx="60" cy="60" r="22" stroke="#c8a35c" strokeWidth="0.8" fill="none" opacity="0.8"/>
        <circle cx="60" cy="60" r="12" stroke="#4ac3d9" strokeWidth="1" fill="none"/>
        <circle cx="60" cy="60" r="3" fill="#e8c47a"/>
      </svg>
    </div>
  );
}

// --- STATE: DROP ---
function AetherDrop({ theme }) {
  return (
    <div style={{
      flex: 1, display:'flex', flexDirection:'column', alignItems:'center',
      justifyContent:'center', gap: 24, padding: 40, position:'relative',
    }}>
      {/* background etchings */}
      <svg style={{ position:'absolute', inset: 0, width: '100%', height: '100%', opacity: 0.08 }}>
        <defs><pattern id="ae-grid-a" width="40" height="40" patternUnits="userSpaceOnUse">
          <path d="M40 0H0V40" stroke="#c8a35c" strokeWidth="0.5" fill="none"/>
        </pattern></defs>
        <rect width="100%" height="100%" fill="url(#ae-grid-a)"/>
      </svg>

      <AllaganSigil size={140} rotating={false} />

      <div style={{ textAlign: 'center', zIndex: 2 }}>
        <div style={{
          fontFamily: theme.uiFont, fontSize: 11, letterSpacing: 4,
          color: theme.goldDim, marginBottom: 8, textTransform: 'uppercase',
        }}>Allagan Eye ⸱ 観測器</div>
        <div style={{
          fontFamily: theme.uiFont, fontSize: 28, fontWeight: 500,
          color: theme.goldBright, letterSpacing: 2, marginBottom: 6,
        }}>録画を捧げよ</div>
        <div style={{
          fontFamily: theme.bodyFont, fontSize: 13, color: theme.textDim,
        }}>MP4 · MKV · AVI · MOV を受け入れます</div>
      </div>

      {/* Drop zone */}
      <AllaganFrame style={{ width: '78%', padding: 2, zIndex: 2 }}>
        <div style={{
          border: `1px dashed ${theme.gold}`, padding: '28px 40px',
          textAlign: 'center', background: 'rgba(200, 163, 92, 0.03)',
        }}>
          <div style={{ fontFamily: theme.bodyFont, fontSize: 13, color: theme.gold, marginBottom: 4 }}>
            ⬦ ここに録画ファイルをドロップ
          </div>
          <div style={{ fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim }}>
            or <span style={{color: theme.cyan, textDecoration: 'underline'}}>参照…</span>
          </div>
        </div>
      </AllaganFrame>

      {/* Recent recordings */}
      <div style={{ width: '78%', zIndex: 2 }}>
        <div style={{
          fontFamily: theme.uiFont, fontSize: 10, letterSpacing: 3,
          color: theme.goldDim, marginBottom: 10, textTransform: 'uppercase',
        }}>──── 直近の録画 ────</div>
        {[
          { name: '2026-04-08 21-14-05.mkv', size: '38.2 GB', dur: '2:50:28' },
          { name: '2026-04-05 20-02-11.mkv', size: '24.1 GB', dur: '1:45:12' },
          { name: '2026-03-28 19-45-33.mkv', size: '52.8 GB', dur: '3:28:40' },
        ].map((r, i) => (
          <div key={i} style={{
            display: 'flex', alignItems: 'center', gap: 12, padding: '8px 12px',
            borderBottom: '1px solid rgba(200, 163, 92, 0.08)',
            fontFamily: theme.monoFont, fontSize: 11, color: theme.text,
          }}>
            <span style={{color: theme.gold}}>◈</span>
            <span style={{flex: 1}}>{r.name}</span>
            <span style={{color: theme.textDim}}>{r.dur}</span>
            <span style={{color: theme.textDim, width: 60, textAlign: 'right'}}>{r.size}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// --- STATE: DETECTING ---
function AetherDetecting({ theme }) {
  // 2フェーズ: Detecting → Refining (scorebar 判定は Refining 内に統合)
  // Splitting は書出し処理の実体なので ⑤ export に移動
  const phases = [
    { name: 'Detecting', jp: '粗スキャン',  pct: 100, time: '5:50', sub: '3410 samples · 31 blackouts' },
    { name: 'Refining',  jp: '精密計測',    pct: 62,  time: '1:11', sub: '9 / 15 境界を確認中' },
  ];
  return (
    <div style={{
      flex: 1, display:'flex', flexDirection:'column',
      padding: 24, gap: 20, position:'relative',
    }}>
      {/* Top: active sigil + source info */}
      <div style={{ display:'flex', gap: 20, alignItems:'center' }}>
        <AllaganSigil size={84} rotating={true} />
        <div style={{flex: 1}}>
          <div style={{fontFamily: theme.uiFont, fontSize: 10, letterSpacing: 3, color: theme.goldDim, textTransform:'uppercase'}}>観測中</div>
          <div style={{fontFamily: theme.bodyFont, fontSize: 14, color: theme.textBright, marginTop: 4}}>2026-04-08 21-14-05.mkv</div>
          <div style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim, marginTop: 3}}>
            2:50:28 · 1920×1080 · 60fps · h264 · GPU (RTX 5090)
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{fontFamily: theme.uiFont, fontSize: 32, color: theme.goldBright, letterSpacing: 1}}>81%</div>
          <div style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim}}>経過 7:01 · 残り 1:38</div>
        </div>
      </div>

      <div style={{height: 1, background: `linear-gradient(90deg, transparent, ${theme.gold}, transparent)`, opacity: 0.4}} />

      {/* 4 phases */}
      <div style={{display:'flex', flexDirection:'column', gap: 14}}>
        {phases.map((p, i) => (
          <div key={i}>
            <div style={{display:'flex', alignItems: 'baseline', marginBottom: 6, gap: 12, fontFamily: theme.bodyFont, fontSize: 12}}>
              <span style={{
                fontFamily: theme.uiFont, letterSpacing: 1.5,
                color: p.pct === 100 ? theme.cyan : (p.pct > 0 ? theme.goldBright : theme.textDim),
                width: 90,
              }}>{p.name}</span>
              <span style={{color: theme.textDim, fontSize: 11}}>{p.jp}</span>
              <span style={{flex: 1}} />
              <span style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim}}>{p.sub}</span>
              <span style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.gold, width: 40, textAlign:'right'}}>{p.time}</span>
            </div>
            {/* progress bar */}
            <div style={{height: 4, background: 'rgba(200, 163, 92, 0.1)', position: 'relative', overflow: 'hidden'}}>
              <div style={{
                position: 'absolute', left: 0, top: 0, bottom: 0,
                width: `${p.pct}%`,
                background: p.pct === 100
                  ? `linear-gradient(90deg, ${theme.cyan}, ${theme.cyanBright})`
                  : `linear-gradient(90deg, ${theme.goldDim}, ${theme.goldBright})`,
                boxShadow: p.pct < 100 && p.pct > 0 ? `0 0 8px ${theme.gold}` : 'none',
              }}/>
              {p.pct > 0 && p.pct < 100 && (
                <div style={{
                  position: 'absolute', top: 0, bottom: 0, width: 2,
                  left: `${p.pct}%`, background: theme.goldBright,
                  boxShadow: `0 0 6px ${theme.goldBright}`,
                }}/>
              )}
            </div>
          </div>
        ))}
      </div>

      <div style={{height: 1, background: `linear-gradient(90deg, transparent, ${theme.gold}, transparent)`, opacity: 0.4}} />

      {/* Live log */}
      <div style={{
        flex: 1, background: theme.bgDeep, padding: 12,
        fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim,
        overflow: 'hidden', lineHeight: 1.6,
        border: '1px solid rgba(200, 163, 92, 0.08)',
      }}>
        <div><span style={{color: theme.cyan}}>[00:05:50]</span> 粗スキャン完了: 3410 samples, 31 blackouts</div>
        <div><span style={{color: theme.cyan}}>[00:06:53]</span> 境界候補 18 領域を精密計測中…</div>
        <div><span style={{color: theme.goldBright}}>[00:07:01]</span> 境界 9/15 を解析中 <span style={{color: theme.gold}}>▓▓▓▓▓▓░░░░</span></div>
        <div style={{color: theme.goldDim}}>  → 試合境界として確定</div>
        <div style={{color: theme.goldDim}}>  → 試合境界でない (除外)</div>
      </div>
    </div>
  );
}

// --- STATE: COMPLETE ---
function AetherComplete({ theme }) {
  const meta = window.AE_META;
  const samples = window.AE_BRIGHTNESS;
  const [selected, setSelected] = useState(4);
  const match = meta.matches[selected - 1];

  const W = 700, H = 100;
  const path = buildBrightnessPath(samples, W, H);
  const matches = meta.matches;

  return (
    <div style={{
      flex: 1, display:'flex', flexDirection:'column',
      padding: 20, gap: 14, position:'relative',
    }}>
      {/* Top bar: source + status */}
      <div style={{display:'flex', alignItems:'center', gap: 16}}>
        <div style={{
          width: 8, height: 8, borderRadius: '50%', background: theme.cyan,
          boxShadow: `0 0 10px ${theme.cyan}`,
        }}/>
        <div style={{flex: 1}}>
          <div style={{fontFamily: theme.uiFont, fontSize: 10, letterSpacing: 3, color: theme.goldDim, textTransform:'uppercase'}}>観測完了</div>
          <div style={{fontFamily: theme.bodyFont, fontSize: 13, color: theme.textBright, marginTop: 2}}>2026-04-08 21-14-05.mkv</div>
        </div>
        <div style={{display:'flex', gap: 24, fontFamily: theme.monoFont, fontSize: 10}}>
          <div><div style={{color: theme.textDim}}>試合数</div><div style={{color: theme.goldBright, fontSize: 16, fontFamily: theme.uiFont}}>{matches.length}</div></div>
          <div><div style={{color: theme.textDim}}>所要</div><div style={{color: theme.goldBright, fontSize: 16, fontFamily: theme.uiFont}}>07:58</div></div>
          <div><div style={{color: theme.textDim}}>総尺</div><div style={{color: theme.goldBright, fontSize: 16, fontFamily: theme.uiFont}}>{meta.source_duration_display}</div></div>
        </div>
      </div>

      {/* Timeline (brightness + blackouts + matches) */}
      <AllaganFrame style={{padding: 12, background: theme.bgDeep, border: theme.panelBorder}}>
        <div style={{fontFamily: theme.uiFont, fontSize: 9, letterSpacing: 2.5, color: theme.goldDim, marginBottom: 8}}>輝度 ⸱ BRIGHTNESS TIMELINE</div>
        <svg viewBox={`0 0 ${W} ${H + 48}`} style={{width: '100%', height: 'auto', display: 'block'}} preserveAspectRatio="none">
          {/* grid */}
          {[50, 100, 150, 200].map(y => (
            <line key={y} x1={0} x2={W} y1={H - (y/255)*H} y2={H - (y/255)*H} stroke={theme.gold} strokeOpacity="0.08" strokeWidth="0.5"/>
          ))}
          <line x1={0} x2={W} y1={H - (15/255)*H} y2={H - (15/255)*H} stroke={theme.danger} strokeOpacity="0.4" strokeDasharray="3 3" strokeWidth="0.5"/>
          <text x={4} y={H - (15/255)*H - 2} fontSize="7" fill={theme.danger} fontFamily={theme.monoFont}>threshold=15</text>

          {/* Blackout regions (behind line) */}
          {findBlackoutRegions(samples, meta.source_duration, 15).map((r, i) => {
            const x1 = (r.start / meta.source_duration) * W;
            const x2 = (r.end / meta.source_duration) * W;
            return <rect key={i} x={x1} y={0} width={Math.max(1.5, x2-x1)} height={H} fill={theme.cyan} fillOpacity="0.12"/>;
          })}

          {/* Brightness line */}
          <path d={path} stroke={theme.gold} strokeWidth="0.8" fill="none" opacity="0.9"/>
          <path d={path + ` L ${W} ${H} L 0 ${H} Z`} fill={theme.gold} fillOpacity="0.06"/>

          {/* Match segments (below) */}
          {matches.map((m, i) => {
            const x1 = (m.start_time / meta.source_duration) * W;
            const x2 = (m.end_time / meta.source_duration) * W;
            const isSel = i + 1 === selected;
            return (
              <g key={i} onClick={() => setSelected(i + 1)} style={{cursor:'pointer'}}>
                <rect
                  x={x1} y={H + 6} width={Math.max(2, x2 - x1)} height={18}
                  fill={m.type === 'fl_match' ? theme.gold : theme.goldDim}
                  opacity={isSel ? 1 : 0.55}
                  stroke={isSel ? theme.goldBright : 'none'} strokeWidth={isSel ? 1 : 0}
                />
                <text x={x1 + 2} y={H + 18} fontSize="7" fill={theme.bg} fontFamily={theme.monoFont} fontWeight="600">
                  {String(m.index).padStart(2,'0')}
                </text>
              </g>
            );
          })}

          {/* Time axis */}
          {[0, 0.25, 0.5, 0.75, 1].map(p => (
            <g key={p}>
              <line x1={p*W} x2={p*W} y1={H + 30} y2={H + 34} stroke={theme.goldDim} strokeWidth="0.5"/>
              <text x={p*W} y={H + 44} fontSize="7" fill={theme.textDim} fontFamily={theme.monoFont} textAnchor={p === 0 ? 'start' : p === 1 ? 'end' : 'middle'}>
                {fmtTime(p * meta.source_duration)}
              </text>
            </g>
          ))}
        </svg>
      </AllaganFrame>

      {/* Match list + preview */}
      <div style={{flex: 1, display:'flex', gap: 14, minHeight: 0}}>
        {/* Match list */}
        <div style={{flex: 1, background: theme.bgDeep, border: theme.panelBorder, overflow:'hidden', display: 'flex', flexDirection:'column'}}>
          <div style={{padding: '8px 12px', borderBottom: `1px solid ${theme.gold}22`, fontFamily: theme.uiFont, fontSize: 9, letterSpacing: 2.5, color: theme.goldDim}}>
            試合一覧 ⸱ MATCHES
          </div>
          <div style={{flex: 1, overflow:'auto'}}>
            {matches.map((m) => {
              const isSel = m.index === selected;
              return (
                <div key={m.index} onClick={() => setSelected(m.index)} style={{
                  display:'flex', alignItems:'center', gap: 10, padding: '8px 12px',
                  cursor:'pointer',
                  background: isSel ? 'rgba(200, 163, 92, 0.1)' : 'transparent',
                  borderLeft: isSel ? `2px solid ${theme.gold}` : '2px solid transparent',
                }}>
                  <MatchThumb index={m.index} theme={theme} w={48} h={27} />
                  <div style={{flex: 1, minWidth: 0}}>
                    <div style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.goldBright}}>
                      MATCH_{String(m.index).padStart(3,'0')}
                    </div>
                    <div style={{fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim}}>
                      {m.start_display} → {m.end_display} · {m.duration_display}
                    </div>
                  </div>
                  <div style={{
                    fontFamily: theme.uiFont, fontSize: 8, letterSpacing: 1.2,
                    padding: '2px 6px', textTransform: 'uppercase',
                    border: `1px solid ${m.type === 'fl_match' ? theme.cyan : theme.goldDim}`,
                    color: m.type === 'fl_match' ? theme.cyan : theme.goldDim,
                  }}>{m.type === 'fl_match' ? 'FL' : '?'}</div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Preview */}
        <div style={{width: 280, display: 'flex', flexDirection: 'column', gap: 10}}>
          <AllaganFrame style={{padding: 8, background: theme.bgDeep, border: theme.panelBorder}}>
            <div style={{aspectRatio: '16/9', background: '#000', position: 'relative', overflow: 'hidden'}}>
              <MatchThumb index={match.index} theme={theme} w="100%" h="100%" />
              <div style={{
                position:'absolute', inset: 0, display:'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <div style={{
                  width: 32, height: 32, border: `1px solid ${theme.goldBright}`,
                  borderRadius: '50%', display:'flex', alignItems:'center', justifyContent:'center',
                  background: 'rgba(0,0,0,0.4)', backdropFilter:'blur(2px)',
                }}>
                  <div style={{
                    width: 0, height: 0, borderLeft: `8px solid ${theme.goldBright}`,
                    borderTop: '5px solid transparent', borderBottom: '5px solid transparent',
                    marginLeft: 3,
                  }}/>
                </div>
              </div>
              <div style={{position:'absolute', bottom: 4, right: 6, fontFamily: theme.monoFont, fontSize: 9, color: '#fff', background:'rgba(0,0,0,0.6)', padding:'1px 4px'}}>
                {match.duration_display}
              </div>
            </div>
          </AllaganFrame>
          <div style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.text, lineHeight: 1.7}}>
            <div style={{color: theme.goldBright, fontSize: 11, marginBottom: 4}}>match_{String(match.index).padStart(3,'0')}.mp4</div>
            <div><span style={{color: theme.textDim}}>開始   </span>{match.start_display}</div>
            <div><span style={{color: theme.textDim}}>終了   </span>{match.end_display}</div>
            <div><span style={{color: theme.textDim}}>長さ   </span>{match.duration_display}</div>
            <div><span style={{color: theme.textDim}}>分類   </span><span style={{color: match.type === 'fl_match' ? theme.cyan : theme.goldDim}}>{match.type}</span></div>
          </div>
          <button style={{
            marginTop: 'auto', padding: '10px 16px',
            background: `linear-gradient(180deg, ${theme.gold}, ${theme.goldDim})`,
            border: 'none', color: theme.bg,
            fontFamily: theme.uiFont, fontSize: 11, letterSpacing: 3,
            textTransform: 'uppercase', cursor: 'pointer',
          }}>⬦ 出力フォルダを開く</button>
        </div>
      </div>
    </div>
  );
}

// Main artboard wrapper
function AetherApp({ state, setState }) {
  const theme = aetherTheme;
  return (
    <div style={{
      width: '100%', height: '100%',
      background: theme.bg, color: theme.text,
      display: 'flex', flexDirection: 'column',
      position: 'relative', overflow: 'hidden',
    }}>
      <StateSwitcher state={state} setState={setState} theme={theme} />
      <WindowChrome title="Allagan Eye" theme={theme} />
      {/* Side rail */}
      <div style={{flex: 1, display: 'flex', minHeight: 0}}>
        <div style={{
          width: 48, background: theme.bgDeep,
          borderRight: `1px solid ${theme.gold}22`,
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          padding: '16px 0', gap: 20, color: theme.gold,
        }}>
          <div style={{fontFamily: theme.uiFont, fontSize: 18, color: theme.goldBright, transform:'rotate(-90deg)', marginTop: 30, letterSpacing: 4, whiteSpace:'nowrap'}}>ALLAGAN</div>
          <div style={{flex: 1}} />
          {['◈','◇','◆','⎊'].map((c, i) => (
            <div key={i} style={{
              width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: i === 0 ? theme.goldBright : theme.goldDim, fontSize: 14,
              border: i === 0 ? `1px solid ${theme.gold}` : '1px solid transparent',
            }}>{c}</div>
          ))}
        </div>
        <div style={{flex: 1, display: 'flex', flexDirection: 'column', position: 'relative', minWidth: 0}}>
          {state === 'drop' && <AetherDrop theme={theme} />}
          {state === 'detecting' && <AetherDetecting theme={theme} />}
          {state === 'complete' && <AetherComplete theme={theme} />}
        </div>
      </div>
    </div>
  );
}

window.AetherApp = AetherApp;
window.aetherTheme = aetherTheme;
