// Variant C: "Eorzea Ops" — hybrid tactical workbench
// Dark slate base, gold accents (FF14 nod), cyan/green neon for live data.
// Calm and dense — feels like a pro editor.

const opsTheme = {
  name: 'Eorzea Ops',
  uiFont: '"Inter", "Segoe UI", sans-serif',
  bodyFont: '"Inter", "Segoe UI", sans-serif',
  monoFont: '"JetBrains Mono", "Consolas", monospace',
  bg: '#14161c',
  bgDeep: '#0d0f14',
  panel: '#1b1e26',
  panelAlt: '#222631',
  panelBorder: '1px solid #2a2f3c',
  gold: '#d4b26a',
  goldDim: '#8c7543',
  cyan: '#5cc4d9',
  green: '#6adc8f',
  magenta: '#c46ed0',
  text: '#d8dde6',
  textDim: '#7a8295',
  textBright: '#ffffff',
  danger: '#e67a7a',
  chromeBg: '#0d0f14',
  chromeFg: '#d8dde6',
  chromeBorder: '1px solid #2a2f3c',
  switcherBg: 'rgba(13, 15, 20, 0.9)',
  switcherBorder: '1px solid #2a2f3c',
  switcherActiveBg: '#d4b26a',
  switcherActiveFg: '#14161c',
  switcherFg: '#7a8295',
  thumbBg: 'linear-gradient(135deg, #2a2f3c, #14161c)',
  thumbBorder: '1px solid #2a2f3c',
};

function OpsPanel({ children, style = {}, title, accent }) {
  return (
    <div style={{
      background: opsTheme.panel, border: opsTheme.panelBorder, borderRadius: 4,
      display: 'flex', flexDirection: 'column', minHeight: 0, ...style,
    }}>
      {title && (
        <div style={{
          padding: '6px 10px', fontSize: 10, letterSpacing: 1.5,
          color: accent || opsTheme.textDim, textTransform: 'uppercase',
          fontWeight: 600, borderBottom: '1px solid #2a2f3c',
          display: 'flex', alignItems: 'center', gap: 6,
        }}>
          {accent && <div style={{width: 6, height: 6, borderRadius: '50%', background: accent}}/>}
          {title}
        </div>
      )}
      {children}
    </div>
  );
}

// --- DROP ---
function OpsDrop({ theme }) {
  return (
    <div style={{flex: 1, padding: 20, display: 'grid', gridTemplateColumns: '1fr 280px', gap: 12, minHeight: 0}}>
      {/* Big drop zone */}
      <OpsPanel style={{padding: 0, overflow: 'hidden'}}>
        <div style={{
          flex: 1, border: `1.5px dashed ${theme.gold}66`, margin: 14, borderRadius: 4,
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          gap: 16, background: `radial-gradient(ellipse at center, ${theme.gold}08, transparent 70%)`,
        }}>
          {/* Hexagon pile icon */}
          <svg width="80" height="80" viewBox="0 0 80 80">
            <polygon points="40,6 68,22 68,54 40,70 12,54 12,22" stroke={theme.gold} strokeWidth="1" fill="none" opacity="0.8"/>
            <polygon points="40,18 58,28 58,48 40,58 22,48 22,28" stroke={theme.gold} strokeWidth="0.5" fill="none" opacity="0.5"/>
            <path d="M40 30 V46 M32 38 H48" stroke={theme.cyan} strokeWidth="1.5"/>
          </svg>
          <div style={{textAlign:'center'}}>
            <div style={{fontFamily: theme.bodyFont, fontSize: 18, fontWeight: 600, color: theme.textBright, marginBottom: 4}}>
              録画ファイルをドロップ
            </div>
            <div style={{fontFamily: theme.bodyFont, fontSize: 12, color: theme.textDim}}>
              または <span style={{color: theme.cyan, cursor:'pointer', textDecoration:'underline'}}>参照…</span> ·  <span style={{fontFamily: theme.monoFont, fontSize: 11}}>MP4 / MKV / AVI / MOV</span>
            </div>
          </div>
          <div style={{display:'flex', gap: 20, marginTop: 10, fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim}}>
            <span><span style={{color: theme.green}}>●</span> ffmpeg 8.1</span>
            <span><span style={{color: theme.green}}>●</span> GPU: RTX 5090</span>
            <span><span style={{color: theme.green}}>●</span> 1359 GB free</span>
          </div>
        </div>
      </OpsPanel>

      {/* Right rail: recent + presets */}
      <div style={{display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0}}>
        <OpsPanel title="直近の録画" accent={theme.gold} style={{flex: 1}}>
          <div style={{flex: 1, overflow: 'auto'}}>
            {[
              { name: '2026-04-08 21-14-05.mkv', size: '38.2 GB', dur: '2:50:28', m: 9, date: '4月8日' },
              { name: '2026-04-05 20-02-11.mkv', size: '24.1 GB', dur: '1:45:12', m: 6, date: '4月5日' },
              { name: '2026-03-28 19-45-33.mkv', size: '52.8 GB', dur: '3:28:40', m: 11, date: '3月28日' },
              { name: '2026-03-22 21-30-00.mkv', size: '18.7 GB', dur: '1:18:22', m: 4, date: '3月22日' },
            ].map((r, i) => (
              <div key={i} style={{padding: '8px 10px', borderBottom: '1px solid #22262f', cursor: 'pointer'}}>
                <div style={{display:'flex', alignItems:'center', gap: 6}}>
                  <div style={{width: 6, height: 6, borderRadius: 1, background: theme.gold}}/>
                  <span style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.text}}>{r.name}</span>
                </div>
                <div style={{display:'flex', gap: 10, marginTop: 3, marginLeft: 12, fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim}}>
                  <span>{r.dur}</span>
                  <span>{r.m}試合</span>
                  <span style={{marginLeft: 'auto'}}>{r.date}</span>
                </div>
              </div>
            ))}
          </div>
        </OpsPanel>

        <OpsPanel title="検知プリセット" accent={theme.cyan}>
          <div style={{padding: 10, fontFamily: theme.bodyFont, fontSize: 11}}>
            {[
              { n: 'フロントライン (標準)', sub: 'sample=1.0s · min_match=300s', active: true },
              { n: '短尺 / 練習用', sub: 'sample=0.5s · min_match=60s', active: false },
              { n: 'カスタム…', sub: '', active: false },
            ].map((p, i) => (
              <div key={i} style={{
                padding: '6px 8px', borderRadius: 3, marginBottom: 2, cursor: 'pointer',
                background: p.active ? `${theme.cyan}15` : 'transparent',
                borderLeft: p.active ? `2px solid ${theme.cyan}` : '2px solid transparent',
              }}>
                <div style={{color: p.active ? theme.cyan : theme.text, fontWeight: p.active ? 600 : 400}}>{p.n}</div>
                {p.sub && <div style={{fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim, marginTop: 1}}>{p.sub}</div>}
              </div>
            ))}
          </div>
        </OpsPanel>
      </div>
    </div>
  );
}

// --- DETECTING ---
function OpsDetecting({ theme }) {
  const phases = [
    { n: 'Detecting', jp: '粗スキャン', pct: 100, sub: '3410 samples · 31 blackouts', time: '5:50' },
    { n: 'Refining',  jp: '精密計測',   pct: 100, sub: '18 regions refined',          time: '1:03' },
    { n: 'Scorebar',  jp: 'スコアバー', pct: 62,  sub: '9 / 15 boundaries probed',    time: '0:08' },
    { n: 'Splitting', jp: '分割',       pct: 0,   sub: 'pending',                     time: '—' },
  ];
  return (
    <div style={{flex: 1, padding: 16, display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0}}>
      {/* Header row */}
      <OpsPanel style={{padding: 14}}>
        <div style={{display:'flex', alignItems:'center', gap: 14}}>
          {/* Spinner */}
          <div style={{position: 'relative', width: 52, height: 52}}>
            <svg viewBox="0 0 52 52" style={{position: 'absolute', inset: 0, animation: 'ops-spin 2s linear infinite'}}>
              <circle cx="26" cy="26" r="22" stroke={theme.gold} strokeWidth="1.5" fill="none" strokeDasharray="8 5" opacity="0.6"/>
            </svg>
            <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: theme.monoFont, fontSize: 14, color: theme.gold, fontWeight: 600}}>62%</div>
          </div>
          <div style={{flex: 1}}>
            <div style={{fontSize: 11, color: theme.textDim, letterSpacing: 2, textTransform: 'uppercase'}}>検知実行中</div>
            <div style={{fontSize: 15, color: theme.textBright, fontWeight: 600, marginTop: 2}}>2026-04-08 21-14-05.mkv</div>
            <div style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim, marginTop: 3}}>
              2:50:28 · 1920×1080 @60 · h264 · <span style={{color: theme.green}}>GPU (RTX 5090)</span> · workers=16
            </div>
          </div>
          <div style={{display: 'flex', gap: 18}}>
            <div style={{textAlign: 'center'}}>
              <div style={{fontSize: 9, color: theme.textDim, letterSpacing: 1.5, textTransform: 'uppercase'}}>経過</div>
              <div style={{fontFamily: theme.monoFont, fontSize: 18, color: theme.text, fontWeight: 600, marginTop: 2}}>07:01</div>
            </div>
            <div style={{textAlign: 'center'}}>
              <div style={{fontSize: 9, color: theme.textDim, letterSpacing: 1.5, textTransform: 'uppercase'}}>残り</div>
              <div style={{fontFamily: theme.monoFont, fontSize: 18, color: theme.gold, fontWeight: 600, marginTop: 2}}>04:12</div>
            </div>
            <button style={{
              alignSelf: 'center', padding: '6px 14px', background: 'transparent',
              border: `1px solid ${theme.danger}66`, color: theme.danger,
              fontSize: 11, borderRadius: 3, cursor: 'pointer',
            }}>中止</button>
          </div>
        </div>
      </OpsPanel>

      {/* Phase pipeline */}
      <OpsPanel title="パイプライン" accent={theme.gold}>
        <div style={{padding: 14, display: 'flex', flexDirection: 'column', gap: 12}}>
          {phases.map((p, i) => {
            const done = p.pct === 100;
            const active = p.pct > 0 && p.pct < 100;
            return (
              <div key={i} style={{display: 'flex', alignItems: 'center', gap: 12}}>
                {/* Step circle */}
                <div style={{
                  width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 10, fontWeight: 700, fontFamily: theme.monoFont,
                  background: done ? theme.green : (active ? theme.gold : theme.panelAlt),
                  color: done || active ? theme.bg : theme.textDim,
                  boxShadow: active ? `0 0 10px ${theme.gold}aa` : 'none',
                }}>{done ? '✓' : i + 1}</div>
                <div style={{width: 160, display: 'flex', flexDirection: 'column'}}>
                  <div style={{fontSize: 12, fontWeight: 600, color: active ? theme.gold : (done ? theme.text : theme.textDim)}}>
                    {p.n} <span style={{fontWeight: 400, fontSize: 11, color: theme.textDim}}>{p.jp}</span>
                  </div>
                  <div style={{fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim, marginTop: 1}}>{p.sub}</div>
                </div>
                {/* Bar */}
                <div style={{flex: 1, height: 6, background: theme.bgDeep, borderRadius: 3, overflow: 'hidden', position: 'relative'}}>
                  <div style={{
                    width: `${p.pct}%`, height: '100%',
                    background: done ? theme.green : (active ? `linear-gradient(90deg, ${theme.goldDim}, ${theme.gold})` : theme.panelAlt),
                    boxShadow: active ? `0 0 8px ${theme.gold}88` : 'none',
                    transition: 'width 0.3s',
                  }}/>
                  {active && (
                    <div style={{position: 'absolute', inset: 0, width: `${p.pct}%`,
                      background: 'repeating-linear-gradient(90deg, transparent 0 6px, rgba(255,255,255,0.18) 6px 8px)',
                      animation: 'ops-stripe 0.8s linear infinite'}}/>
                  )}
                </div>
                <div style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim, width: 48, textAlign: 'right'}}>{p.time}</div>
                <div style={{fontFamily: theme.monoFont, fontSize: 11, color: done ? theme.green : (active ? theme.gold : theme.textDim), width: 40, textAlign: 'right', fontWeight: 600}}>
                  {p.pct}%
                </div>
              </div>
            );
          })}
        </div>
      </OpsPanel>

      {/* Bottom: preview timeline (live brightness) + log */}
      <div style={{flex: 1, display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 12, minHeight: 0}}>
        <OpsPanel title="輝度プレビュー (検知中)" accent={theme.cyan}>
          <div style={{padding: 12, flex: 1, display: 'flex', flexDirection: 'column'}}>
            <svg viewBox="0 0 400 100" style={{width: '100%', height: '100%'}} preserveAspectRatio="none">
              {/* Progressive path — only show first 62% */}
              {(() => {
                const samples = window.AE_BRIGHTNESS;
                const cut = Math.floor(samples.length * 0.62);
                const partial = samples.slice(0, cut);
                const fullPath = buildBrightnessPath(partial, 400 * 0.62, 100);
                return (<>
                  <path d={fullPath} stroke={theme.cyan} strokeWidth="0.8" fill="none" opacity="0.9"/>
                  <path d={fullPath + ` L ${400*0.62} 100 L 0 100 Z`} fill={theme.cyan} fillOpacity="0.12"/>
                  {/* Playhead */}
                  <line x1={400*0.62} x2={400*0.62} y1={0} y2={100} stroke={theme.gold} strokeWidth="1"/>
                  <circle cx={400*0.62} cy={0} r="3" fill={theme.gold}/>
                </>);
              })()}
              {/* threshold line */}
              <line x1={0} x2={400} y1={100 - (15/255)*100} y2={100 - (15/255)*100}
                stroke={theme.danger} strokeOpacity="0.4" strokeDasharray="3 3" strokeWidth="0.5"/>
            </svg>
            <div style={{display: 'flex', justifyContent: 'space-between', fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim, marginTop: 4}}>
              <span>00:00</span>
              <span style={{color: theme.gold}}>▲ 1:45:38 (現在位置)</span>
              <span>2:50:28</span>
            </div>
          </div>
        </OpsPanel>

        <OpsPanel title="ライブログ" accent={theme.green} style={{overflow: 'hidden'}}>
          <div style={{flex: 1, padding: 10, fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim, lineHeight: 1.7, overflow: 'hidden'}}>
            <div><span style={{color: theme.green}}>[05:50.1]</span> Pass 1 complete: 31 blackouts</div>
            <div><span style={{color: theme.green}}>[06:53.2]</span> Pass 2 complete: 18 regions</div>
            <div><span style={{color: theme.cyan}}>[07:01.2]</span> scorebar r=9/15 σ=58.2 → <span style={{color: theme.green}}>match_boundary</span></div>
            <div><span style={{color: theme.cyan}}>[07:01.4]</span> scorebar r=10/15 σ=12.4 → <span style={{color: theme.danger}}>non_fl</span></div>
            <div><span style={{color: theme.cyan}}>[07:01.7]</span> scorebar r=11/15 σ=61.8 → <span style={{color: theme.green}}>match_boundary</span></div>
            <div><span style={{color: theme.gold}}>[07:01.9]</span> gpu.util=74% mem=4.2/32GB</div>
          </div>
        </OpsPanel>
      </div>
      <style>{`
        @keyframes ops-spin { to { transform: rotate(360deg); } }
        @keyframes ops-stripe { to { background-position: 14px 0; } }
      `}</style>
    </div>
  );
}

// --- COMPLETE ---
function OpsComplete({ theme }) {
  const meta = window.AE_META;
  const samples = window.AE_BRIGHTNESS;
  const [selected, setSelected] = useState(4);
  const match = meta.matches[selected - 1];
  const W = 720, H = 80;
  const path = buildBrightnessPath(samples, W, H);

  return (
    <div style={{flex: 1, padding: 16, display: 'grid', gridTemplateRows: 'auto auto 1fr', gap: 12, minHeight: 0}}>
      {/* Header */}
      <OpsPanel style={{padding: '10px 14px'}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 14}}>
          <div style={{width: 10, height: 10, borderRadius: '50%', background: theme.green, boxShadow: `0 0 8px ${theme.green}`}}/>
          <div style={{flex: 1}}>
            <div style={{fontSize: 10, color: theme.green, letterSpacing: 2, textTransform: 'uppercase', fontWeight: 600}}>検知完了</div>
            <div style={{fontSize: 13, color: theme.textBright, marginTop: 2, fontWeight: 500}}>2026-04-08 21-14-05.mkv</div>
          </div>
          {[
            { l: '試合数', v: meta.matches.length },
            { l: 'FL_MATCH', v: meta.matches.filter(m=>m.type==='fl_match').length },
            { l: 'UNKNOWN', v: meta.matches.filter(m=>m.type==='unknown').length },
            { l: '総尺', v: meta.source_duration_display },
            { l: '所要', v: '07:58' },
          ].map((s, i) => (
            <div key={i} style={{paddingLeft: 18, borderLeft: i === 0 ? '1px solid #2a2f3c' : '1px solid #2a2f3c'}}>
              <div style={{fontSize: 9, color: theme.textDim, letterSpacing: 1.5, textTransform: 'uppercase'}}>{s.l}</div>
              <div style={{fontFamily: theme.monoFont, fontSize: 16, color: theme.gold, fontWeight: 600, marginTop: 1}}>{s.v}</div>
            </div>
          ))}
        </div>
      </OpsPanel>

      {/* Timeline */}
      <OpsPanel title="タイムライン" accent={theme.gold}>
        <div style={{padding: 12}}>
          <svg viewBox={`0 0 ${W} ${H + 56}`} style={{width: '100%', height: 'auto', display: 'block'}} preserveAspectRatio="none">
            {/* grid */}
            {[0, 64, 128, 192].map(y => (
              <line key={y} x1={0} x2={W} y1={H - (y/255)*H} y2={H - (y/255)*H} stroke="#2a2f3c" strokeWidth="0.4"/>
            ))}
            {/* threshold */}
            <line x1={0} x2={W} y1={H - (15/255)*H} y2={H - (15/255)*H}
              stroke={theme.danger} strokeOpacity="0.4" strokeDasharray="3 3" strokeWidth="0.5"/>
            <text x={W - 4} y={H - (15/255)*H - 2} fontSize="7" fill={theme.danger} fontFamily={theme.monoFont} textAnchor="end">
              threshold=15
            </text>

            {/* Blackout bands */}
            {findBlackoutRegions(samples, meta.source_duration, 15).map((r, i) => {
              const x1 = (r.start / meta.source_duration) * W;
              const x2 = (r.end / meta.source_duration) * W;
              return <rect key={i} x={x1} y={0} width={Math.max(1.5, x2-x1)} height={H} fill={theme.danger} fillOpacity="0.15"/>;
            })}

            {/* Brightness */}
            <path d={path + ` L ${W} ${H} L 0 ${H} Z`} fill={theme.cyan} fillOpacity="0.08"/>
            <path d={path} stroke={theme.cyan} strokeWidth="0.8" fill="none"/>

            {/* Match blocks */}
            {meta.matches.map((m, i) => {
              const x1 = (m.start_time / meta.source_duration) * W;
              const x2 = (m.end_time / meta.source_duration) * W;
              const isSel = m.index === selected;
              const isFl = m.type === 'fl_match';
              return (
                <g key={i} onClick={() => setSelected(m.index)} style={{cursor: 'pointer'}}>
                  <rect x={x1} y={H + 4} width={Math.max(2, x2 - x1)} height={20}
                    fill={isFl ? theme.gold : theme.textDim}
                    fillOpacity={isSel ? 1 : 0.5}
                    stroke={isSel ? theme.goldDim : 'none'} strokeWidth={isSel ? 1.5 : 0}/>
                  {x2 - x1 > 18 && (
                    <text x={x1 + 4} y={H + 17} fontSize="8" fill={theme.bg} fontFamily={theme.monoFont} fontWeight="700">
                      {String(m.index).padStart(2, '0')}
                    </text>
                  )}
                </g>
              );
            })}

            {/* Axis */}
            {[0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1].map(p => (
              <g key={p}>
                <line x1={p*W} x2={p*W} y1={H + 28} y2={H + 32} stroke={theme.textDim} strokeWidth="0.4"/>
                {[0, 0.25, 0.5, 0.75, 1].includes(p) && (
                  <text x={p*W} y={H + 44} fontSize="8" fill={theme.textDim} fontFamily={theme.monoFont}
                    textAnchor={p === 0 ? 'start' : p === 1 ? 'end' : 'middle'}>
                    {fmtTime(p * meta.source_duration)}
                  </text>
                )}
              </g>
            ))}
          </svg>
        </div>
      </OpsPanel>

      {/* Bottom: match list + preview */}
      <div style={{display: 'grid', gridTemplateColumns: '1fr 320px', gap: 12, minHeight: 0}}>
        <OpsPanel title={`試合一覧 · ${meta.matches.length} matches`} accent={theme.gold}>
          <div style={{flex: 1, overflow: 'auto'}}>
            <table style={{width: '100%', borderCollapse: 'collapse', fontFamily: theme.bodyFont, fontSize: 11}}>
              <thead>
                <tr style={{background: theme.bgDeep, position: 'sticky', top: 0}}>
                  {['#', 'サムネ', 'ファイル', '開始', '終了', '長さ', '分類', ''].map((h, i) => (
                    <th key={i} style={{
                      textAlign: 'left', padding: '6px 10px', fontSize: 9,
                      letterSpacing: 1, color: theme.textDim, fontWeight: 600, textTransform: 'uppercase',
                      borderBottom: '1px solid #2a2f3c',
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {meta.matches.map((m) => {
                  const isSel = m.index === selected;
                  return (
                    <tr key={m.index} onClick={() => setSelected(m.index)} style={{
                      cursor: 'pointer',
                      background: isSel ? `${theme.gold}18` : 'transparent',
                      borderLeft: isSel ? `2px solid ${theme.gold}` : '2px solid transparent',
                    }}>
                      <td style={{padding: '6px 10px', fontFamily: theme.monoFont, color: theme.gold, fontWeight: 600}}>
                        {String(m.index).padStart(2, '0')}
                      </td>
                      <td style={{padding: '4px 10px'}}><MatchThumb index={m.index} theme={theme} w={48} h={27} /></td>
                      <td style={{padding: '6px 10px', fontFamily: theme.monoFont, fontSize: 10, color: theme.text}}>
                        match_{String(m.index).padStart(3, '0')}.mp4
                      </td>
                      <td style={{padding: '6px 10px', fontFamily: theme.monoFont, color: theme.textDim}}>{m.start_display}</td>
                      <td style={{padding: '6px 10px', fontFamily: theme.monoFont, color: theme.textDim}}>{m.end_display}</td>
                      <td style={{padding: '6px 10px', fontFamily: theme.monoFont, color: theme.text}}>{m.duration_display}</td>
                      <td style={{padding: '6px 10px'}}>
                        <span style={{
                          fontFamily: theme.monoFont, fontSize: 9, padding: '2px 6px', borderRadius: 2,
                          background: m.type === 'fl_match' ? `${theme.green}22` : `${theme.textDim}22`,
                          color: m.type === 'fl_match' ? theme.green : theme.textDim,
                          border: `1px solid ${m.type === 'fl_match' ? theme.green : theme.textDim}44`,
                        }}>{m.type}</span>
                      </td>
                      <td style={{padding: '6px 10px', color: theme.textDim, fontSize: 11}}>···</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </OpsPanel>

        <div style={{display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0}}>
          <OpsPanel title={`match_${String(match.index).padStart(3,'0')}.mp4`} accent={theme.cyan}>
            <div style={{padding: 10, display: 'flex', flexDirection: 'column', gap: 10}}>
              <div style={{aspectRatio: '16/9', background: '#000', position: 'relative', borderRadius: 3, overflow: 'hidden'}}>
                <MatchThumb index={match.index} theme={theme} w="100%" h="100%" />
                <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
                  <div style={{width: 40, height: 40, borderRadius: '50%', background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', border: `1px solid ${theme.gold}`}}>
                    <div style={{width: 0, height: 0, borderLeft: `10px solid ${theme.gold}`, borderTop: '6px solid transparent', borderBottom: '6px solid transparent', marginLeft: 3}}/>
                  </div>
                </div>
                <div style={{position: 'absolute', bottom: 6, right: 8, fontFamily: theme.monoFont, fontSize: 10, color: theme.text, background: 'rgba(0,0,0,0.6)', padding: '1px 6px', borderRadius: 2}}>
                  {match.duration_display}
                </div>
              </div>
              <div style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.text, display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '4px 10px'}}>
                <span style={{color: theme.textDim}}>index</span><span>{match.index}</span>
                <span style={{color: theme.textDim}}>start</span><span>{match.start_display} <span style={{color: theme.textDim}}>({match.start_time.toFixed(1)}s)</span></span>
                <span style={{color: theme.textDim}}>end</span><span>{match.end_display} <span style={{color: theme.textDim}}>({match.end_time.toFixed(1)}s)</span></span>
                <span style={{color: theme.textDim}}>duration</span><span>{match.duration_display}</span>
                <span style={{color: theme.textDim}}>type</span>
                <span style={{color: match.type === 'fl_match' ? theme.green : theme.textDim}}>{match.type}</span>
              </div>
            </div>
          </OpsPanel>

          <div style={{display: 'flex', gap: 8, marginTop: 'auto'}}>
            <button style={{
              flex: 1, padding: '10px', background: theme.gold, border: 'none', borderRadius: 3,
              color: theme.bg, fontFamily: theme.bodyFont, fontSize: 12, fontWeight: 600, cursor: 'pointer',
            }}>出力フォルダ</button>
            <button style={{
              flex: 1, padding: '10px', background: 'transparent', border: `1px solid ${theme.cyan}`, borderRadius: 3,
              color: theme.cyan, fontFamily: theme.bodyFont, fontSize: 12, fontWeight: 600, cursor: 'pointer',
            }}>metadata.json</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function OpsApp({ state, setState }) {
  const theme = opsTheme;
  return (
    <div style={{width: '100%', height: '100%', background: theme.bg, color: theme.text,
      display: 'flex', flexDirection: 'column', position: 'relative', overflow: 'hidden'}}>
      <StateSwitcher state={state} setState={setState} theme={theme} />

      {/* Custom chrome with menu bar */}
      <div style={{
        height: 34, background: theme.chromeBg, borderBottom: theme.chromeBorder,
        display: 'flex', alignItems: 'center', padding: '0 12px', gap: 14, userSelect: 'none',
      }}>
        <div style={{display: 'flex', gap: 6}}>
          <div style={{width: 11, height: 11, borderRadius: '50%', background: '#ff5f57'}}/>
          <div style={{width: 11, height: 11, borderRadius: '50%', background: '#febc2e'}}/>
          <div style={{width: 11, height: 11, borderRadius: '50%', background: '#28c840'}}/>
        </div>
        <div style={{display:'flex', gap: 4, alignItems:'center', marginLeft: 10}}>
          <div style={{width: 12, height: 12, background: theme.gold,
            clipPath: 'polygon(50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%)'}}/>
          <span style={{fontFamily: theme.bodyFont, fontSize: 12, color: theme.textBright, fontWeight: 600, marginLeft: 6}}>Allagan Eye</span>
        </div>
        <div style={{display:'flex', gap: 14, marginLeft: 10, fontFamily: theme.bodyFont, fontSize: 11, color: theme.textDim}}>
          <span>ファイル</span><span>編集</span><span>表示</span><span>検知</span><span>ヘルプ</span>
        </div>
        <div style={{flex: 1}}/>
        <div style={{fontFamily: theme.monoFont, fontSize: 10, color: theme.textDim}}>v0.1.1</div>
      </div>

      <div style={{flex: 1, display: 'flex', minHeight: 0}}>
        {/* Sidebar */}
        <div style={{
          width: 180, background: theme.bgDeep, borderRight: theme.panelBorder,
          display: 'flex', flexDirection: 'column', padding: '12px 0',
        }}>
          {[
            { i: '◈', n: 'インポート', active: true },
            { i: '◇', n: '検知履歴' },
            { i: '◆', n: 'ハイライト', badge: 'L5' },
            { i: '⚙', n: '設定' },
          ].map((it, i) => (
            <div key={i} style={{
              padding: '8px 14px', display: 'flex', alignItems: 'center', gap: 10,
              background: it.active ? `${theme.gold}15` : 'transparent',
              borderLeft: it.active ? `2px solid ${theme.gold}` : '2px solid transparent',
              fontFamily: theme.bodyFont, fontSize: 12, color: it.active ? theme.gold : theme.text,
              fontWeight: it.active ? 600 : 400, cursor: 'pointer',
            }}>
              <span style={{fontSize: 14, color: it.active ? theme.gold : theme.textDim}}>{it.i}</span>
              <span style={{flex: 1}}>{it.n}</span>
              {it.badge && <span style={{fontSize: 9, padding: '1px 6px', background: theme.panel, color: theme.textDim, borderRadius: 2, fontFamily: theme.monoFont}}>{it.badge}</span>}
            </div>
          ))}
          <div style={{flex: 1}}/>
          <div style={{padding: '10px 14px', borderTop: '1px solid #22262f'}}>
            <div style={{fontFamily: theme.monoFont, fontSize: 9, color: theme.textDim, lineHeight: 1.6}}>
              <div><span style={{color: theme.green}}>●</span> ffmpeg 8.1</div>
              <div><span style={{color: theme.green}}>●</span> GPU ready</div>
              <div style={{color: theme.textDim, marginTop: 4}}>出力: ./output</div>
            </div>
          </div>
        </div>

        <div style={{flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0}}>
          {state === 'drop' && <OpsDrop theme={theme} />}
          {state === 'detecting' && <OpsDetecting theme={theme} />}
          {state === 'complete' && <OpsComplete theme={theme} />}
        </div>
      </div>
    </div>
  );
}

window.OpsApp = OpsApp;
window.opsTheme = opsTheme;
