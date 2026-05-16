// Aetheric Observatory — Preview/Adjust screen (境界の秒単位調整)
// Two layout variants: A1 = Dual IN/OUT preview (focused single-match mode)
//                      A2 = Full timeline + zoomed detail (dual-scope, waveform + scorebar confidence)

// ═══════════════════════════════════════════════════════════════
// Shared helpers
// ═══════════════════════════════════════════════════════════════

// Build a plausible per-second brightness signal around a given timestamp
// Returns an array of {t, b} for t in [center-window, center+window]
function buildLocalBrightness(centerT, windowSec, sampleHz = 2) {
  const count = windowSec * 2 * sampleHz;
  const out = [];
  for (let i = 0; i < count; i++) {
    const t = centerT - windowSec + (i / sampleHz);
    // Boundary dip: very low within ±1.5s of center
    const distFromEdge = Math.abs(t - centerT);
    let b;
    if (distFromEdge < 1.2) {
      b = 4 + Math.random() * 6;
    } else if (distFromEdge < 2.5) {
      b = 20 + Math.random() * 30;
    } else {
      // In-match or pre-match gameplay
      b = 85 + Math.sin(t * 0.4) * 18 + Math.sin(t * 1.3) * 10 + (Math.random() - 0.5) * 14;
    }
    out.push({ t, b: Math.max(0, Math.min(255, b)) });
  }
  return out;
}

// Format as HH:MM:SS.ff
function fmtPreciseTime(s, fps = 60) {
  const sign = s < 0 ? '-' : '';
  s = Math.abs(s);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  const frames = Math.floor((s - Math.floor(s)) * fps);
  return `${sign}${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}.${String(frames).padStart(2,'0')}`;
}

// Frame strip — generates N thumbnail cells at equal time intervals around t
function FrameStrip({ centerT, windowSec, count = 12, theme, boundaryT, onClickFrame }) {
  const frames = [];
  for (let i = 0; i < count; i++) {
    const t = centerT - windowSec + (i / (count - 1)) * windowSec * 2;
    const isBoundary = Math.abs(t - boundaryT) < windowSec / count;
    // Simulate brightness
    const d = Math.abs(t - boundaryT);
    const brightness = d < 1.2 ? 0.08 : d < 2.5 ? 0.35 : 0.85;
    frames.push({ t, isBoundary, brightness });
  }
  return (
    <div style={{display: 'flex', gap: 2, width: '100%'}}>
      {frames.map((f, i) => (
        <div key={i}
          onClick={() => onClickFrame && onClickFrame(f.t)}
          style={{
            flex: 1, aspectRatio: '16/9', position: 'relative',
            background: `rgba(200, 163, 92, ${f.brightness * 0.4})`,
            border: f.isBoundary ? `1px solid ${theme.goldBright}` : `1px solid ${theme.gold}22`,
            cursor: 'pointer', overflow: 'hidden',
          }}>
          {/* faux frame content */}
          <div style={{
            position: 'absolute', inset: 0,
            background: `radial-gradient(ellipse at ${40+i*3}% ${50+(i%3)*10}%, rgba(232,196,122,${f.brightness * 0.6}), transparent 60%)`,
          }}/>
          {f.brightness < 0.15 && (
            <div style={{position: 'absolute', inset: 0, background: '#000', opacity: 0.85}}/>
          )}
          {f.isBoundary && (
            <div style={{
              position: 'absolute', top: 0, bottom: 0, left: '50%', width: 1,
              background: theme.goldBright, boxShadow: `0 0 4px ${theme.goldBright}`,
            }}/>
          )}
          <div style={{
            position: 'absolute', bottom: 1, left: 2,
            fontFamily: theme.monoFont, fontSize: 7, color: 'rgba(255,255,255,0.7)',
          }}>{fmtPreciseTime(f.t).split('.')[0].split(':').slice(-2).join(':')}</div>
        </div>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// A1 — Dual IN/OUT preview (focused on single match)
// Two big video panes (start+end), strip of candidate frames,
// numeric stepper, fine-timeline below.
// ═══════════════════════════════════════════════════════════════

function AetherPreviewA1({ theme, matchIndex = 4, onBack, onExport }) {
  const meta = window.AE_META;
  const match = meta.matches[matchIndex - 1];
  const [startT, setStartT] = useState(match.start_time);
  const [endT, setEndT] = useState(match.end_time);
  const [editing, setEditing] = useState('start'); // 'start' | 'end'
  const [matchName, setMatchName] = useState(`match_${String(match.index).padStart(3,'0')}`);
  const [matchType, setMatchType] = useState(match.type);

  const currentT = editing === 'start' ? startT : endT;
  const setCurrentT = editing === 'start' ? setStartT : setEndT;

  const origStart = match.start_time;
  const origEnd = match.end_time;
  const delta = currentT - (editing === 'start' ? origStart : origEnd);

  // Blackout candidates near the boundary
  const candidates = editing === 'start'
    ? [origStart - 1.4, origStart - 0.7, origStart, origStart + 0.8, origStart + 1.6, origStart + 2.3]
    : [origEnd - 2.1, origEnd - 1.2, origEnd - 0.5, origEnd, origEnd + 0.6, origEnd + 1.3];

  const nudge = (sec) => setCurrentT(t => Math.max(0, Math.min(meta.source_duration, t + sec)));

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      padding: 18, gap: 12, position: 'relative', minHeight: 0,
    }}>
      {/* Header */}
      <div style={{display: 'flex', alignItems: 'center', gap: 14}}>
        <button onClick={onBack} style={{
          background: 'transparent', border: `1px solid ${theme.gold}44`,
          color: theme.gold, padding: '5px 10px', fontFamily: theme.uiFont,
          fontSize: 10, letterSpacing: 2, cursor: 'pointer', textTransform: 'uppercase',
        }}>◀ 一覧へ</button>
        <div style={{flex: 1}}>
          <div style={{fontFamily: theme.uiFont, fontSize: 9, letterSpacing: 3, color: theme.goldDim, textTransform: 'uppercase'}}>
            境界調整 ⸱ BOUNDARY CALIBRATION
          </div>
          <div style={{display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 3}}>
            <input value={matchName} onChange={e => setMatchName(e.target.value)} style={{
              background: 'transparent', border: 'none', borderBottom: `1px dashed ${theme.goldDim}`,
              color: theme.goldBright, fontFamily: theme.uiFont, fontSize: 18,
              letterSpacing: 1, padding: '2px 0', outline: 'none', width: 220,
            }}/>
            <span style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim}}>
              #{String(match.index).padStart(3, '0')} · of {meta.matches.length}
            </span>
          </div>
        </div>
        <select value={matchType} onChange={e => setMatchType(e.target.value)} style={{
          background: theme.bgDeep, border: `1px solid ${theme.gold}44`,
          color: theme.gold, padding: '5px 10px', fontFamily: theme.monoFont, fontSize: 11,
          outline: 'none',
        }}>
          <option value="fl_match">fl_match</option>
          <option value="unknown">unknown</option>
          <option value="skip">skip</option>
        </select>
        <button onClick={onExport} style={{
          background: `linear-gradient(180deg, ${theme.gold}, ${theme.goldDim})`,
          border: 'none', color: theme.bg, padding: '7px 16px',
          fontFamily: theme.uiFont, fontSize: 11, letterSpacing: 2,
          cursor: 'pointer', textTransform: 'uppercase',
        }}>⬦ 適用 → 書き出し</button>
      </div>

      {/* Dual video panes */}
      <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14}}>
        {[
          { label: 'IN ⸱ 開始点', t: startT, orig: origStart, key: 'start', color: theme.cyan },
          { label: 'OUT ⸱ 終了点', t: endT, orig: origEnd, key: 'end', color: theme.gold },
        ].map(pane => {
          const isActive = editing === pane.key;
          return (
            <div key={pane.key} onClick={() => setEditing(pane.key)} style={{
              border: `1px solid ${isActive ? pane.color : theme.gold + '22'}`,
              background: theme.bgDeep, padding: 8, cursor: 'pointer',
              boxShadow: isActive ? `0 0 14px ${pane.color}44` : 'none',
              transition: 'all 0.15s',
            }}>
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6}}>
                <span style={{fontFamily: theme.uiFont, fontSize: 9, letterSpacing: 2.5, color: isActive ? pane.color : theme.goldDim}}>
                  {pane.label}
                </span>
                <span style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim}}>
                  {pane.t !== pane.orig && <span style={{color: theme.goldBright}}>Δ {(pane.t - pane.orig).toFixed(2)}s · </span>}
                  元 {fmtPreciseTime(pane.orig)}
                </span>
              </div>
              <div style={{
                aspectRatio: '16/9', background: '#000', position: 'relative',
                overflow: 'hidden', border: `1px solid ${theme.gold}22`,
              }}>
                {/* faux frame — dark for boundary */}
                <MatchThumb index={pane.key === 'start' ? match.index : match.index} theme={theme} w="100%" h="100%" />
                <div style={{position: 'absolute', inset: 0, background: '#000', opacity: 0.65}}/>
                {/* overlay crosshair */}
                <div style={{position: 'absolute', top: '50%', left: 0, right: 0, height: 1, background: `${pane.color}66`}}/>
                <div style={{position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: `${pane.color}66`}}/>
                {/* timecode */}
                <div style={{
                  position: 'absolute', bottom: 8, left: 10,
                  fontFamily: theme.monoFont, fontSize: 13,
                  color: pane.color, background: 'rgba(0,0,0,0.7)',
                  padding: '2px 8px', letterSpacing: 1,
                }}>{fmtPreciseTime(pane.t)}</div>
                {/* frame +/- indicator */}
                <div style={{
                  position: 'absolute', top: 6, right: 8,
                  fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim,
                }}>frame {Math.floor(pane.t * 60)}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Active editor: stepper + candidate frames + fine timeline */}
      <div style={{
        border: `1px solid ${theme.gold}22`, background: theme.bgDeep,
        padding: 14, display: 'flex', flexDirection: 'column', gap: 12,
      }}>
        <div style={{display: 'flex', alignItems: 'center', gap: 14}}>
          <span style={{
            fontFamily: theme.uiFont, fontSize: 10, letterSpacing: 3,
            color: editing === 'start' ? theme.cyan : theme.goldBright,
          }}>
            調整中: {editing === 'start' ? '開始点 IN' : '終了点 OUT'}
          </span>
          <div style={{flex: 1}}/>
          {/* Numeric input */}
          <span style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim}}>TC:</span>
          <input value={fmtPreciseTime(currentT)} onChange={() => {}} style={{
            background: theme.bg, border: `1px solid ${theme.gold}44`, color: theme.goldBright,
            fontFamily: theme.monoFont, fontSize: 14, padding: '4px 8px',
            width: 140, outline: 'none', letterSpacing: 1,
          }}/>
        </div>

        {/* Steppers */}
        <div style={{display: 'flex', gap: 6, alignItems: 'center'}}>
          {[
            { l: '−10s', v: -10 }, { l: '−1s', v: -1 }, { l: '−1F', v: -1/60 },
          ].map(b => (
            <button key={b.l} onClick={() => nudge(b.v)} style={{
              background: theme.bg, border: `1px solid ${theme.gold}44`, color: theme.gold,
              padding: '6px 12px', fontFamily: theme.monoFont, fontSize: 11,
              cursor: 'pointer', minWidth: 50,
            }}>{b.l}</button>
          ))}
          <div style={{flex: 1, textAlign: 'center', fontFamily: theme.uiFont, fontSize: 10, color: theme.textDim, letterSpacing: 2}}>
            ← → : 1秒 ⸱ shift: 10秒 ⸱ ⌥: 1フレーム ⸱ space: 再生
          </div>
          {[
            { l: '+1F', v: 1/60 }, { l: '+1s', v: 1 }, { l: '+10s', v: 10 },
          ].map(b => (
            <button key={b.l} onClick={() => nudge(b.v)} style={{
              background: theme.bg, border: `1px solid ${theme.gold}44`, color: theme.gold,
              padding: '6px 12px', fontFamily: theme.monoFont, fontSize: 11,
              cursor: 'pointer', minWidth: 50,
            }}>{b.l}</button>
          ))}
        </div>

        {/* Candidate frames strip */}
        <div>
          <div style={{
            fontFamily: theme.uiFont, fontSize: 9, letterSpacing: 2, color: theme.goldDim,
            marginBottom: 6, display: 'flex', justifyContent: 'space-between',
          }}>
            <span>候補フレーム ⸱ ±3秒ウィンドウ</span>
            <span style={{color: theme.textDim, fontFamily: theme.monoFont}}>12 frames @ 0.5s</span>
          </div>
          <FrameStrip centerT={currentT} windowSec={3} count={12} theme={theme}
            boundaryT={currentT} onClickFrame={(t) => setCurrentT(t)}/>
        </div>

        {/* Fine-zoom timeline */}
        <div>
          <div style={{
            fontFamily: theme.uiFont, fontSize: 9, letterSpacing: 2, color: theme.goldDim,
            marginBottom: 4, display: 'flex', justifyContent: 'space-between',
          }}>
            <span>微細タイムライン ⸱ 輝度 + 黒フェード候補</span>
            <span style={{color: theme.textDim, fontFamily: theme.monoFont}}>zoom ±5s</span>
          </div>
          <div style={{position: 'relative', height: 70, background: theme.bg, border: `1px solid ${theme.gold}22`, overflow: 'hidden'}}>
            <svg viewBox="0 0 400 70" style={{width: '100%', height: '100%', display: 'block'}} preserveAspectRatio="none">
              {/* Grid — each vertical = 1s */}
              {[-5,-4,-3,-2,-1,0,1,2,3,4,5].map(s => {
                const x = ((s + 5) / 10) * 400;
                return <line key={s} x1={x} x2={x} y1={0} y2={70} stroke={theme.gold} strokeOpacity={s === 0 ? 0.4 : 0.1} strokeWidth={0.5}/>;
              })}
              {/* Threshold */}
              <line x1={0} x2={400} y1={70 - (15/255)*55} y2={70 - (15/255)*55}
                stroke={theme.danger} strokeOpacity="0.4" strokeDasharray="2 2" strokeWidth="0.4"/>

              {/* Brightness curve */}
              {(() => {
                const local = buildLocalBrightness(currentT, 5, 10); // 10Hz
                let d = '';
                local.forEach((p, i) => {
                  const x = (i / (local.length - 1)) * 400;
                  const y = 70 - (p.b / 255) * 55;
                  d += (i === 0 ? 'M' : 'L') + x.toFixed(1) + ' ' + y.toFixed(1) + ' ';
                });
                return (<>
                  <path d={d + ` L 400 70 L 0 70 Z`} fill={theme.gold} fillOpacity="0.1"/>
                  <path d={d} stroke={theme.gold} strokeWidth="0.8" fill="none"/>
                </>);
              })()}

              {/* Candidate markers */}
              {candidates.map((cT, i) => {
                const relS = cT - currentT;
                if (Math.abs(relS) > 5) return null;
                const x = ((relS + 5) / 10) * 400;
                const isCurrent = Math.abs(cT - currentT) < 0.05;
                return (
                  <g key={i} onClick={() => setCurrentT(cT)} style={{cursor: 'pointer'}}>
                    <line x1={x} x2={x} y1={0} y2={70}
                      stroke={isCurrent ? theme.goldBright : theme.cyan}
                      strokeOpacity={isCurrent ? 1 : 0.5}
                      strokeWidth={isCurrent ? 1.2 : 0.6}/>
                    <circle cx={x} cy={10} r={isCurrent ? 3 : 2}
                      fill={isCurrent ? theme.goldBright : theme.cyan}/>
                  </g>
                );
              })}
              {/* Center playhead */}
              <line x1={200} x2={200} y1={0} y2={70} stroke={theme.goldBright} strokeWidth="1.2"/>
              <polygon points="196,0 204,0 200,6" fill={theme.goldBright}/>
            </svg>
            {/* Axis labels */}
            <div style={{position: 'absolute', bottom: 0, left: 0, right: 0, display: 'flex', justifyContent: 'space-between',
              padding: '0 4px', fontFamily: theme.monoFont, fontSize: 8, color: theme.textDim, pointerEvents: 'none'}}>
              <span>{fmtPreciseTime(currentT - 5)}</span>
              <span style={{color: theme.goldBright}}>▲ {fmtPreciseTime(currentT)}</span>
              <span>{fmtPreciseTime(currentT + 5)}</span>
            </div>
          </div>
        </div>

        {/* Info line */}
        <div style={{display: 'flex', gap: 20, fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim, paddingTop: 4, borderTop: `1px solid ${theme.gold}11`}}>
          <span>長さ: <span style={{color: theme.goldBright}}>{fmtTime(endT - startT)}</span></span>
          <span>Δ 開始: <span style={{color: startT !== origStart ? theme.goldBright : theme.textDim}}>{(startT - origStart).toFixed(2)}s</span></span>
          <span>Δ 終了: <span style={{color: endT !== origEnd ? theme.goldBright : theme.textDim}}>{(endT - origEnd).toFixed(2)}s</span></span>
          <span style={{marginLeft: 'auto'}}>scorebar信頼度: <span style={{color: theme.cyan}}>σ=58.2 (match)</span></span>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// A2 — Dual-scope: full-timeline top + zoomed detail bottom
// With waveform + scorebar confidence overlay
// ═══════════════════════════════════════════════════════════════

function AetherPreviewA2({ theme, matchIndex = 4, onBack, onExport }) {
  const meta = window.AE_META;
  const samples = window.AE_BRIGHTNESS;
  const [selected, setSelected] = useState(matchIndex);
  const match = meta.matches[selected - 1];
  const [startT, setStartT] = useState(match.start_time);
  const [endT, setEndT] = useState(match.end_time);
  const [editing, setEditing] = useState('start');

  // Reset local edits when match changes
  useEffect(() => {
    setStartT(match.start_time);
    setEndT(match.end_time);
  }, [selected]);

  const W = 900, H = 60;
  const path = buildBrightnessPath(samples, W, H);
  const currentT = editing === 'start' ? startT : endT;
  const origStart = match.start_time, origEnd = match.end_time;

  const dirty = startT !== origStart || endT !== origEnd;

  const nudge = (sec) => {
    if (editing === 'start') setStartT(t => Math.max(0, Math.min(meta.source_duration, t + sec)));
    else setEndT(t => Math.max(0, Math.min(meta.source_duration, t + sec)));
  };

  return (
    <div style={{flex: 1, display: 'flex', flexDirection: 'column', padding: 14, gap: 10, position: 'relative', minHeight: 0}}>
      {/* Header */}
      <div style={{display: 'flex', alignItems: 'center', gap: 14}}>
        <button onClick={onBack} style={{
          background: 'transparent', border: `1px solid ${theme.gold}44`, color: theme.gold,
          padding: '5px 10px', fontFamily: theme.uiFont, fontSize: 10, letterSpacing: 2,
          cursor: 'pointer', textTransform: 'uppercase',
        }}>◀ 一覧</button>
        <div style={{fontFamily: theme.uiFont, fontSize: 9, letterSpacing: 3, color: theme.goldDim, textTransform: 'uppercase'}}>
          境界調整 ⸱ 全体 + 詳細
        </div>
        <div style={{flex: 1}}/>
        {dirty && <span style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.danger}}>● 未保存の変更</span>}
        <button style={{
          background: 'transparent', border: `1px solid ${theme.gold}44`, color: theme.gold,
          padding: '6px 12px', fontFamily: theme.uiFont, fontSize: 10, letterSpacing: 2,
          cursor: 'pointer', textTransform: 'uppercase',
        }}>⊟ 分割</button>
        <button style={{
          background: 'transparent', border: `1px solid ${theme.gold}44`, color: theme.gold,
          padding: '6px 12px', fontFamily: theme.uiFont, fontSize: 10, letterSpacing: 2,
          cursor: 'pointer', textTransform: 'uppercase',
        }}>⊞ 次と結合</button>
        <button style={{
          background: 'transparent', border: `1px solid ${theme.danger}66`, color: theme.danger,
          padding: '6px 12px', fontFamily: theme.uiFont, fontSize: 10, letterSpacing: 2,
          cursor: 'pointer', textTransform: 'uppercase',
        }}>✕ 除外</button>
        <button onClick={onExport} style={{
          background: `linear-gradient(180deg, ${theme.gold}, ${theme.goldDim})`,
          border: 'none', color: theme.bg, padding: '7px 14px',
          fontFamily: theme.uiFont, fontSize: 11, letterSpacing: 2, cursor: 'pointer', textTransform: 'uppercase',
        }}>⬦ 適用</button>
      </div>

      {/* TOP: Full timeline with all matches, selected highlighted */}
      <div style={{background: theme.bgDeep, border: `1px solid ${theme.gold}22`, padding: 10}}>
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
          fontFamily: theme.uiFont, fontSize: 9, letterSpacing: 2, color: theme.goldDim, marginBottom: 4,
        }}>
          <span>全体タイムライン ⸱ FULL</span>
          <span style={{fontFamily: theme.monoFont, color: theme.textDim}}>{meta.source_duration_display}</span>
        </div>
        <svg viewBox={`0 0 ${W} ${H + 30}`} style={{width: '100%', height: 'auto', display: 'block'}} preserveAspectRatio="none">
          {/* blackouts */}
          {findBlackoutRegions(samples, meta.source_duration, 15).map((r, i) => {
            const x1 = (r.start / meta.source_duration) * W;
            const x2 = (r.end / meta.source_duration) * W;
            return <rect key={i} x={x1} y={0} width={Math.max(1, x2-x1)} height={H} fill={theme.cyan} fillOpacity="0.1"/>;
          })}
          {/* brightness */}
          <path d={path} stroke={theme.gold} strokeWidth="0.5" fill="none" opacity="0.7"/>

          {/* match bars */}
          {meta.matches.map((m, i) => {
            const x1 = (m.start_time / meta.source_duration) * W;
            const x2 = (m.end_time / meta.source_duration) * W;
            const isSel = m.index === selected;
            return (
              <g key={i} onClick={() => setSelected(m.index)} style={{cursor: 'pointer'}}>
                <rect x={x1} y={H + 4} width={Math.max(1.5, x2-x1)} height={12}
                  fill={m.type === 'fl_match' ? theme.gold : theme.goldDim}
                  opacity={isSel ? 1 : 0.4}
                  stroke={isSel ? theme.goldBright : 'none'} strokeWidth={isSel ? 1 : 0}/>
              </g>
            );
          })}

          {/* zoom window indicator — ±30s around currentT */}
          {(() => {
            const winStart = Math.max(0, currentT - 30);
            const winEnd = Math.min(meta.source_duration, currentT + 30);
            const x1 = (winStart / meta.source_duration) * W;
            const x2 = (winEnd / meta.source_duration) * W;
            return (
              <g>
                <rect x={x1} y={0} width={Math.max(2, x2-x1)} height={H}
                  fill={theme.cyan} fillOpacity="0.15" stroke={theme.cyan} strokeWidth="1"/>
                <line x1={(currentT/meta.source_duration)*W} x2={(currentT/meta.source_duration)*W}
                  y1={0} y2={H+18} stroke={theme.cyanBright} strokeWidth="1"/>
              </g>
            );
          })()}

          {/* axis ticks */}
          {[0, 0.25, 0.5, 0.75, 1].map(p => (
            <text key={p} x={p*W} y={H + 28} fontSize="8" fill={theme.textDim} fontFamily={theme.monoFont}
              textAnchor={p === 0 ? 'start' : p === 1 ? 'end' : 'middle'}>
              {fmtTime(p * meta.source_duration)}
            </text>
          ))}
        </svg>
      </div>

      {/* MIDDLE: Dual frame preview (smaller) */}
      <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 220px', gap: 10}}>
        {[
          { label: 'IN', t: startT, orig: origStart, key: 'start', color: theme.cyan },
          { label: 'OUT', t: endT, orig: origEnd, key: 'end', color: theme.gold },
        ].map(pane => {
          const isActive = editing === pane.key;
          return (
            <div key={pane.key} onClick={() => setEditing(pane.key)} style={{
              border: `1px solid ${isActive ? pane.color : theme.gold + '22'}`,
              background: theme.bgDeep, padding: 6, cursor: 'pointer',
              boxShadow: isActive ? `0 0 10px ${pane.color}44` : 'none',
            }}>
              <div style={{display: 'flex', justifyContent: 'space-between', fontFamily: theme.uiFont, fontSize: 9, letterSpacing: 2, marginBottom: 4}}>
                <span style={{color: isActive ? pane.color : theme.goldDim}}>{pane.label}</span>
                <span style={{fontFamily: theme.monoFont, color: theme.textDim}}>
                  {pane.t !== pane.orig && <span style={{color: theme.goldBright}}>Δ{(pane.t-pane.orig).toFixed(2)}s </span>}
                  {fmtPreciseTime(pane.t)}
                </span>
              </div>
              <div style={{aspectRatio: '16/9', background: '#000', position: 'relative', overflow: 'hidden'}}>
                <MatchThumb index={match.index} theme={theme} w="100%" h="100%"/>
                <div style={{position: 'absolute', inset: 0, background: '#000', opacity: 0.7}}/>
                <div style={{position: 'absolute', top: '50%', left: 0, right: 0, height: 1, background: `${pane.color}55`}}/>
                <div style={{position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: `${pane.color}55`}}/>
              </div>
            </div>
          );
        })}

        {/* Info panel */}
        <div style={{
          border: `1px solid ${theme.gold}22`, background: theme.bgDeep,
          padding: 8, fontFamily: theme.monoFont, fontSize: 10, color: theme.text,
          display: 'flex', flexDirection: 'column', gap: 3,
        }}>
          <div style={{fontFamily: theme.uiFont, fontSize: 9, letterSpacing: 2, color: theme.goldDim, marginBottom: 2}}>
            #{String(match.index).padStart(3,'0')} · {meta.matches.length}試合中
          </div>
          <div><span style={{color: theme.textDim}}>長さ </span><span style={{color: theme.goldBright}}>{fmtTime(endT-startT)}</span></div>
          <div><span style={{color: theme.textDim}}>type </span>
            <span style={{color: match.type === 'fl_match' ? theme.cyan : theme.goldDim}}>{match.type}</span>
          </div>
          <div style={{marginTop: 'auto', display: 'flex', gap: 4}}>
            <button style={{flex: 1, background: 'transparent', border: `1px solid ${theme.gold}44`, color: theme.gold, padding: '3px', fontFamily: theme.uiFont, fontSize: 9, letterSpacing: 1.5, cursor: 'pointer'}}>◀ 前</button>
            <button style={{flex: 1, background: 'transparent', border: `1px solid ${theme.gold}44`, color: theme.gold, padding: '3px', fontFamily: theme.uiFont, fontSize: 9, letterSpacing: 1.5, cursor: 'pointer'}}>次 ▶</button>
          </div>
        </div>
      </div>

      {/* BOTTOM: Zoomed detail with waveform + scorebar confidence */}
      <div style={{
        flex: 1, background: theme.bgDeep, border: `1px solid ${theme.gold}22`,
        padding: 10, display: 'flex', flexDirection: 'column', gap: 6, minHeight: 0,
      }}>
        <div style={{display: 'flex', alignItems: 'baseline', gap: 14}}>
          <span style={{fontFamily: theme.uiFont, fontSize: 9, letterSpacing: 2, color: editing === 'start' ? theme.cyan : theme.goldBright}}>
            詳細: {editing === 'start' ? 'IN 開始点' : 'OUT 終了点'} ⸱ ±30秒
          </span>
          <span style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim}}>
            {fmtPreciseTime(currentT - 30)} — {fmtPreciseTime(currentT + 30)}
          </span>
          <div style={{flex: 1}}/>
          {/* stepper */}
          {[
            { l: '−10s', v: -10 }, { l: '−1s', v: -1 }, { l: '−1F', v: -1/60 },
            { l: '+1F', v: 1/60 }, { l: '+1s', v: 1 }, { l: '+10s', v: 10 },
          ].map(b => (
            <button key={b.l} onClick={() => nudge(b.v)} style={{
              background: theme.bg, border: `1px solid ${theme.gold}44`, color: theme.gold,
              padding: '3px 8px', fontFamily: theme.monoFont, fontSize: 10,
              cursor: 'pointer', minWidth: 42,
            }}>{b.l}</button>
          ))}
        </div>

        {/* Stacked: brightness / waveform / scorebar / candidates */}
        <div style={{flex: 1, display: 'flex', flexDirection: 'column', gap: 4, minHeight: 0}}>
          {/* Brightness */}
          <LaneChart theme={theme} label="輝度" labelColor={theme.gold} centerT={currentT} editing={editing}>
            {(() => {
              const local = buildLocalBrightness(currentT, 30, 4);
              let d = '';
              local.forEach((p, i) => {
                const x = (i / (local.length - 1)) * 900;
                const y = 50 - (p.b / 255) * 45;
                d += (i === 0 ? 'M' : 'L') + x.toFixed(1) + ' ' + y.toFixed(1) + ' ';
              });
              return (<>
                <path d={d + ` L 900 50 L 0 50 Z`} fill={theme.gold} fillOpacity="0.12"/>
                <path d={d} stroke={theme.gold} strokeWidth="0.8" fill="none"/>
                <line x1={0} x2={900} y1={50-(15/255)*45} y2={50-(15/255)*45}
                  stroke={theme.danger} strokeOpacity="0.4" strokeDasharray="3 3" strokeWidth="0.4"/>
              </>);
            })()}
          </LaneChart>

          {/* Audio waveform */}
          <LaneChart theme={theme} label="音声" labelColor={theme.cyan} centerT={currentT} editing={editing}>
            {(() => {
              // synthetic waveform: quiet near boundary
              const bars = [];
              for (let i = 0; i < 180; i++) {
                const relS = -30 + (i / 179) * 60;
                const near = Math.abs(relS) < 2;
                const mid = Math.abs(relS) < 5;
                const amp = near ? 2 + Math.random() * 3 : mid ? 6 + Math.random() * 8 : 12 + Math.random() * 22;
                const x = (i / 179) * 900;
                bars.push(<rect key={i} x={x - 1.5} y={25 - amp/2} width={3} height={amp} fill={theme.cyan} fillOpacity="0.5"/>);
              }
              return bars;
            })()}
          </LaneChart>

          {/* Scorebar confidence */}
          <LaneChart theme={theme} label="Scorebar" labelColor={theme.goldBright} centerT={currentT} editing={editing}>
            {(() => {
              // Step function: 1.0 inside match, drops to 0 at boundary
              const pts = [];
              for (let i = 0; i < 100; i++) {
                const relS = -30 + (i / 99) * 60;
                // In-match (relS before currentT if start, after if end) = 1
                const isInMatch = editing === 'start' ? relS >= 0 : relS <= 0;
                const transition = Math.abs(relS) < 1.5 ? Math.min(1, Math.abs(relS) / 1.5) : 1;
                const v = isInMatch ? transition : 0.12 + Math.random() * 0.05;
                pts.push({ x: (i / 99) * 900, v });
              }
              let d = '';
              pts.forEach((p, i) => {
                const y = 50 - p.v * 45;
                d += (i === 0 ? 'M' : 'L') + p.x.toFixed(1) + ' ' + y.toFixed(1) + ' ';
              });
              return (<>
                <path d={d + ` L 900 50 L 0 50 Z`} fill={theme.goldBright} fillOpacity="0.1"/>
                <path d={d} stroke={theme.goldBright} strokeWidth="0.8" fill="none"/>
              </>);
            })()}
          </LaneChart>

          {/* Candidate boundary markers */}
          <div style={{
            height: 38, position: 'relative', background: theme.bg,
            border: `1px solid ${theme.gold}11`,
          }}>
            <div style={{
              position: 'absolute', top: 2, left: 6,
              fontFamily: theme.uiFont, fontSize: 8, letterSpacing: 1.5, color: theme.goldDim,
            }}>候補 ⸱ CANDIDATES</div>
            {/* current playhead */}
            <div style={{
              position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1,
              background: theme.goldBright, boxShadow: `0 0 4px ${theme.goldBright}`,
            }}/>
            {/* frame thumbnails at 3s intervals */}
            {[-24, -18, -12, -6, 0, 6, 12, 18, 24].map(offset => {
              const leftPct = ((offset + 30) / 60) * 100;
              const cT = currentT + offset;
              const darkness = Math.abs(offset) < 3 ? 0.9 : Math.abs(offset) < 8 ? 0.5 : 0.15;
              return (
                <div key={offset} onClick={() => nudge(offset)}
                  style={{
                    position: 'absolute', left: `${leftPct}%`, top: 12, width: 36, height: 20,
                    transform: 'translateX(-50%)', background: `rgba(0,0,0,${darkness})`,
                    border: `1px solid ${theme.gold}55`, cursor: 'pointer',
                    fontFamily: theme.monoFont, fontSize: 7, color: theme.goldBright,
                    display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
                    paddingBottom: 1,
                  }}>
                  {offset >= 0 ? '+' : ''}{offset}s
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer axis */}
        <div style={{display: 'flex', justifyContent: 'space-between', fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim, padding: '0 60px'}}>
          <span>−30s</span><span>−15s</span>
          <span style={{color: theme.goldBright}}>▲ {fmtPreciseTime(currentT)}</span>
          <span>+15s</span><span>+30s</span>
        </div>
      </div>
    </div>
  );
}

// Lane chart helper — row with left label and SVG children
function LaneChart({ children, theme, label, labelColor, centerT, editing }) {
  return (
    <div style={{
      flex: 1, display: 'flex', alignItems: 'stretch', gap: 6, minHeight: 0,
      background: theme.bg, border: `1px solid ${theme.gold}11`,
    }}>
      <div style={{
        width: 60, padding: '4px 6px',
        fontFamily: theme.uiFont, fontSize: 8, letterSpacing: 1.5,
        color: labelColor, borderRight: `1px solid ${theme.gold}22`,
        display: 'flex', alignItems: 'center',
      }}>{label}</div>
      <div style={{flex: 1, position: 'relative', minWidth: 0}}>
        <svg viewBox="0 0 900 50" style={{width: '100%', height: '100%', display: 'block'}} preserveAspectRatio="none">
          {/* vertical gridlines every 5s */}
          {[-30,-25,-20,-15,-10,-5,0,5,10,15,20,25,30].map(s => {
            const x = ((s + 30) / 60) * 900;
            return <line key={s} x1={x} x2={x} y1={0} y2={50} stroke={theme.gold} strokeOpacity={s === 0 ? 0.5 : 0.08} strokeWidth={s === 0 ? 0.6 : 0.3}/>;
          })}
          {children}
        </svg>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Export step — small confirmation screen used by both variants
// ═══════════════════════════════════════════════════════════════

function AetherExport({ theme, onBack }) {
  const meta = window.AE_META;
  const [codec, setCodec] = useState('copy');
  const [namePattern, setNamePattern] = useState('match_{idx:03}.mp4');
  const [outDir] = useState('./output');
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (!running) return;
    const iv = setInterval(() => {
      setProgress(p => {
        if (p >= 100) { clearInterval(iv); return 100; }
        return p + 2;
      });
    }, 80);
    return () => clearInterval(iv);
  }, [running]);

  return (
    <div style={{flex: 1, display: 'flex', flexDirection: 'column', padding: 24, gap: 16, position: 'relative'}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 14}}>
        <button onClick={onBack} style={{
          background: 'transparent', border: `1px solid ${theme.gold}44`, color: theme.gold,
          padding: '5px 10px', fontFamily: theme.uiFont, fontSize: 10, letterSpacing: 2,
          cursor: 'pointer', textTransform: 'uppercase',
        }}>◀ プレビュー</button>
        <div>
          <div style={{fontFamily: theme.uiFont, fontSize: 9, letterSpacing: 3, color: theme.goldDim, textTransform: 'uppercase'}}>エクスポート</div>
          <div style={{fontFamily: theme.uiFont, fontSize: 20, color: theme.goldBright, marginTop: 2, letterSpacing: 1}}>
            {meta.matches.length} 試合を書き出す
          </div>
        </div>
      </div>

      <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, flex: 1, minHeight: 0}}>
        {/* Settings */}
        <div style={{background: theme.bgDeep, border: `1px solid ${theme.gold}22`, padding: 14, display: 'flex', flexDirection: 'column', gap: 14}}>
          <div style={{fontFamily: theme.uiFont, fontSize: 9, letterSpacing: 2, color: theme.goldDim}}>設定</div>

          <div>
            <div style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim, marginBottom: 4}}>出力先</div>
            <div style={{display: 'flex', gap: 6}}>
              <input value={outDir} readOnly style={{
                flex: 1, background: theme.bg, border: `1px solid ${theme.gold}44`, color: theme.text,
                fontFamily: theme.monoFont, fontSize: 11, padding: '6px 8px', outline: 'none',
              }}/>
              <button style={{background: 'transparent', border: `1px solid ${theme.gold}44`, color: theme.gold, padding: '6px 12px', fontFamily: theme.uiFont, fontSize: 10, cursor: 'pointer'}}>参照…</button>
            </div>
          </div>

          <div>
            <div style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim, marginBottom: 4}}>命名規則</div>
            <input value={namePattern} onChange={e => setNamePattern(e.target.value)} style={{
              width: '100%', background: theme.bg, border: `1px solid ${theme.gold}44`, color: theme.text,
              fontFamily: theme.monoFont, fontSize: 11, padding: '6px 8px', outline: 'none',
            }}/>
            <div style={{fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim, marginTop: 4}}>
              変数: {`{idx}`} {`{idx:03}`} {`{start}`} {`{type}`} {`{date}`}
            </div>
          </div>

          <div>
            <div style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim, marginBottom: 4}}>コーデック</div>
            <div style={{display: 'flex', gap: 6}}>
              {[
                { v: 'copy', l: '無損失 copy', sub: '高速 / 前Iフレーム吸着' },
                { v: 'h264', l: 'H.264 再エンコード', sub: '遅い / 正確な秒指定' },
              ].map(c => (
                <button key={c.v} onClick={() => setCodec(c.v)} style={{
                  flex: 1, padding: 10, background: codec === c.v ? `${theme.gold}22` : 'transparent',
                  border: `1px solid ${codec === c.v ? theme.gold : theme.gold + '44'}`,
                  color: codec === c.v ? theme.goldBright : theme.text,
                  fontFamily: theme.uiFont, fontSize: 11, cursor: 'pointer', textAlign: 'left',
                }}>
                  <div style={{fontWeight: 600}}>{c.l}</div>
                  <div style={{fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim, marginTop: 2}}>{c.sub}</div>
                </button>
              ))}
            </div>
          </div>

          <div style={{marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 10}}>
            {/* Aggregate progress bar — shown while running or after complete */}
            {running && (
              <div>
                <div style={{
                  display: 'flex', justifyContent: 'space-between',
                  fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim, marginBottom: 4,
                }}>
                  <span style={{color: theme.goldBright, fontFamily: theme.uiFont, letterSpacing: 2}}>
                    {progress < 100 ? '分割・書き出し中' : '完了'}
                  </span>
                  <span>
                    {Math.min(meta.matches.length, Math.floor((progress / 100) * meta.matches.length) + (progress < 100 ? 1 : 0))}
                    {' / '}{meta.matches.length} files
                    <span style={{marginLeft: 12, color: theme.goldBright}}>{progress}%</span>
                  </span>
                </div>
                <div style={{height: 8, background: theme.bg, border: `1px solid ${theme.gold}33`, position: 'relative', overflow: 'hidden'}}>
                  <div style={{
                    position: 'absolute', left: 0, top: 0, bottom: 0, width: `${progress}%`,
                    background: progress < 100
                      ? `linear-gradient(90deg, ${theme.goldDim}, ${theme.goldBright})`
                      : `linear-gradient(90deg, ${theme.cyan}, ${theme.cyanBright})`,
                    boxShadow: progress < 100 ? `0 0 10px ${theme.gold}` : 'none',
                    transition: 'width 0.2s',
                  }}/>
                  {progress > 0 && progress < 100 && (
                    <div style={{
                      position: 'absolute', inset: 0, width: `${progress}%`,
                      background: 'repeating-linear-gradient(90deg, transparent 0 8px, rgba(255,255,255,0.18) 8px 10px)',
                    }}/>
                  )}
                </div>
                <div style={{
                  display: 'flex', justifyContent: 'space-between', marginTop: 4,
                  fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim,
                }}>
                  <span>経過 {fmtTime(progress * 1.2)}</span>
                  <span>残り {progress < 100 ? fmtTime((100 - progress) * 1.2) : '—'}</span>
                </div>
              </div>
            )}
            <button onClick={() => { setRunning(true); setProgress(0); }}
              disabled={running && progress < 100}
              style={{
                width: '100%', padding: '12px 16px',
                background: running && progress < 100
                  ? theme.goldDim
                  : `linear-gradient(180deg, ${theme.gold}, ${theme.goldDim})`,
                border: 'none', color: theme.bg,
                fontFamily: theme.uiFont, fontSize: 13, letterSpacing: 3,
                textTransform: 'uppercase', cursor: running && progress < 100 ? 'default' : 'pointer',
              }}>
              {!running ? '⬦ 書き出し開始' : progress < 100 ? '書き出し中…' : '✓ 完了 — フォルダを開く'}
            </button>
          </div>
        </div>

        {/* Match list preview */}
        <div style={{background: theme.bgDeep, border: `1px solid ${theme.gold}22`, padding: 10, display: 'flex', flexDirection: 'column', minHeight: 0}}>
          <div style={{fontFamily: theme.uiFont, fontSize: 9, letterSpacing: 2, color: theme.goldDim, marginBottom: 6, padding: '4px 4px 0'}}>
            書き出し一覧 ⸱ {meta.matches.length} ファイル
          </div>
          <div style={{flex: 1, overflow: 'auto'}}>
            {meta.matches.map(m => {
              const pct = running ? Math.max(0, Math.min(100, (progress - (m.index - 1) * 11))) : 0;
              const done = running && progress >= m.index * 11;
              return (
                <div key={m.index} style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '6px 8px',
                  borderBottom: `1px solid ${theme.gold}11`,
                  fontFamily: theme.monoFont, fontSize: 10, color: theme.text,
                }}>
                  <span style={{color: done ? theme.cyan : theme.gold, width: 16}}>{done ? '✓' : pct > 0 ? '●' : '○'}</span>
                  <span style={{flex: 1}}>
                    {namePattern.replace('{idx:03}', String(m.index).padStart(3,'0')).replace('{idx}', m.index).replace('{type}', m.type).replace('{start}', m.start_display.replace(/:/g, '-')).replace('{date}', '2026-04-08')}
                  </span>
                  <span style={{color: theme.textDim}}>{m.duration_display}</span>
                  {running && (
                    <div style={{width: 60, height: 3, background: theme.bg, position: 'relative'}}>
                      <div style={{position: 'absolute', left: 0, top: 0, bottom: 0, width: `${pct}%`,
                        background: done ? theme.cyan : theme.gold}}/>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// App wrappers — full flow with 5 states (drop/detecting/complete/preview/export)
// Exposes 2 variants: AetherAppA1 uses PreviewA1, AetherAppA2 uses PreviewA2
// ═══════════════════════════════════════════════════════════════

const FULL_STATES = ['drop', 'detecting', 'complete', 'preview', 'export'];
const FULL_LABELS = { drop: 'インポート', detecting: '検知中', complete: '一覧', preview: '境界調整', export: '書出し' };

function FullStateSwitcher({ state, setState, theme }) {
  return (
    <div style={{
      position: 'absolute', top: 8, right: 8, zIndex: 50,
      display: 'flex', gap: 4, padding: 4,
      background: theme.switcherBg, border: theme.switcherBorder,
      borderRadius: 20, backdropFilter: 'blur(8px)', fontFamily: theme.uiFont,
    }}>
      {FULL_STATES.map(s => (
        <button key={s} onClick={() => setState(s)} style={{
          padding: '4px 10px', fontSize: 10, fontWeight: 600,
          letterSpacing: 0.4, border: 'none', borderRadius: 14, cursor: 'pointer',
          background: state === s ? theme.switcherActiveBg : 'transparent',
          color: state === s ? theme.switcherActiveFg : theme.switcherFg,
          transition: 'all 0.15s',
        }}>{FULL_LABELS[s]}</button>
      ))}
    </div>
  );
}

function makeAetherFullApp(PreviewComponent) {
  return function AetherFullApp({ state, setState }) {
    const theme = aetherTheme;
    return (
      <div style={{
        width: '100%', height: '100%', background: theme.bg, color: theme.text,
        display: 'flex', flexDirection: 'column', position: 'relative', overflow: 'hidden',
      }}>
        <FullStateSwitcher state={state} setState={setState} theme={theme}/>
        <WindowChrome title="Allagan Eye" theme={theme}/>
        <div style={{flex: 1, display: 'flex', minHeight: 0}}>
          <div style={{
            width: 48, background: theme.bgDeep,
            borderRight: `1px solid ${theme.gold}22`,
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            padding: '16px 0', gap: 20, color: theme.gold,
          }}>
            <div style={{fontFamily: theme.uiFont, fontSize: 18, color: theme.goldBright, transform:'rotate(-90deg)', marginTop: 30, letterSpacing: 4, whiteSpace: 'nowrap'}}>ALLAGAN</div>
            <div style={{flex: 1}}/>
            {['◈','◇','◆','⎊'].map((c, i) => (
              <div key={i} style={{
                width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: i === 0 ? theme.goldBright : theme.goldDim, fontSize: 14,
                border: i === 0 ? `1px solid ${theme.gold}` : '1px solid transparent',
              }}>{c}</div>
            ))}
          </div>
          <div style={{flex: 1, display: 'flex', flexDirection: 'column', position: 'relative', minWidth: 0}}>
            {state === 'drop' && <AetherDrop theme={theme}/>}
            {state === 'detecting' && <AetherDetecting theme={theme}/>}
            {state === 'complete' && <AetherComplete theme={theme}/>}
            {state === 'preview' && <PreviewComponent theme={theme} matchIndex={4} onBack={() => setState('complete')} onExport={() => setState('export')}/>}
            {state === 'export' && <AetherExport theme={theme} onBack={() => setState('preview')}/>}
          </div>
        </div>
      </div>
    );
  };
}

window.AetherFullAppA1 = makeAetherFullApp(AetherPreviewA1);
window.AetherFullAppA2 = makeAetherFullApp(AetherPreviewA2);
