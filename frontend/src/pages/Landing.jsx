import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

/* ═══════════════════════════════════════════════════════════════════════════
   Landing — "Signal over noise."

   THE STORY (this is the whole page, in order):
       Returns → Signal → Intelligence → Decision → Recovery

   What this page is NOT about: parcels, trucks, warehouses, shipping. A
   return arriving is a *measurement*. The product's job is to pull an
   estimate out of it and act. So the page is an instrument panel, not a
   logistics brochure.

   ─────────────────────────────────────────────────────────────────────────
   ⚠ THE SCROLL-SYNC ENGINE BELOW IS CARRIED OVER UNCHANGED.
   Video scrubbing, the rAF throttle, the listeners and the cleanup are
   byte-for-byte the previous implementation. Do not refactor it.
   ═══════════════════════════════════════════════════════════════════════ */

/* Type over the dark scrim needs light values — the palette inverted, not
   replaced. Bone stays Bone; it just carries the text now. */
const C = {
  graphite: '#15171B',
  bone: '#EDE9E3',
  vermillion: '#DE4B22',
  vermillionLift: '#E86A45',
  iron: '#6B7078',
  ash: '#C9C3B9',
  sulphur: '#E3C04A',
  onDark: '#E9E4DC',
  onDarkMuted: '#A9A296',
}

const MONO = "'Martian Mono', ui-monospace, monospace"
const HEAD = "'Cabinet Grotesk', system-ui, sans-serif"
const BODY = "'Switzer', system-ui, sans-serif"

/* The five stages. This array *is* the narrative — the nav, the pipeline
   diagram and the section eyebrows all read from it, so they can never
   drift out of sync with each other. */
const STAGES = [
  { id: 'returns',      n: '01', name: 'Returns',      gloss: 'the measurement arrives' },
  { id: 'signal',       n: '02', name: 'Signal',       gloss: 'noise is separated out' },
  { id: 'intelligence', n: '03', name: 'Intelligence', gloss: 'the estimate is formed' },
  { id: 'decision',     n: '04', name: 'Decision',     gloss: 'the estimate is acted on' },
  { id: 'recovery',     n: '05', name: 'Recovery',     gloss: 'value returns to the ledger' },
]

export default function Landing() {
  const navigate = useNavigate()
  const scrollVideoRef = useRef(null)
  const truckVideoRef = useRef(null)
  const [scrollY, setScrollY] = useState(0)
  const [navSolid, setNavSolid] = useState(false)
  const [progress, setProgress] = useState(0)

  // ── SCROLL → VIDEO SCRUB ENGINE ──────────────────────────────────────────
  // UNCHANGED. Only addition: `setProgress`, which reuses the value the
  // engine already computes rather than reading scroll a second time.
  useEffect(() => {
    const video = scrollVideoRef.current
    if (!video) return

    const sync = () => {
      const scrollable = document.documentElement.scrollHeight - window.innerHeight
      if (scrollable > 0 && video.duration) {
        const p = Math.min(window.scrollY / scrollable, 1)
        video.currentTime = p * video.duration
        setProgress(p)
      }
      setScrollY(window.scrollY)
      setNavSolid(window.scrollY > 60)
    }

    video.addEventListener('loadedmetadata', sync)

    let ticking = false
    const onScroll = () => {
      if (!ticking) {
        requestAnimationFrame(() => { sync(); ticking = false })
        ticking = true
      }
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', sync)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', sync)
      video.removeEventListener('loadedmetadata', sync)
    }
  }, [])

  // ── AMBIENT VIDEO — autoplay loop ─────────────────────────────────────────
  useEffect(() => {
    const v = truckVideoRef.current
    if (v) v.play().catch(() => {})
  }, [])

  // ── SECTION REVEALS ──────────────────────────────────────────────────────
  const [vis, setVis] = useState({})
  useEffect(() => {
    const els = document.querySelectorAll('[data-reveal]')
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach(e => {
          if (e.isIntersecting) setVis(v => ({ ...v, [e.target.dataset.reveal]: true }))
        })
      },
      { threshold: 0.15 }
    )
    els.forEach(el => obs.observe(el))
    return () => obs.disconnect()
  }, [])

  const revealed = (key, delay = 0) => ({
    opacity: vis[key] ? 1 : 0,
    transform: vis[key] ? 'translateY(0)' : 'translateY(28px)',
    transition: `opacity 760ms cubic-bezier(0.16,1,0.3,1) ${delay}ms, transform 760ms cubic-bezier(0.16,1,0.3,1) ${delay}ms`,
  })

  return (
    <div style={{ background: C.graphite, color: C.onDark, fontFamily: BODY, overflowX: 'hidden' }}>

      {/* ── FIXED SCROLL VIDEO BACKGROUND ─────────────────────────────────
          The video is pushed almost to black and desaturated — it is
          texture, not content. Nothing on this page asks you to look at it
          directly. */}
      <div style={{ position: 'fixed', inset: 0, zIndex: 1, overflow: 'hidden', background: C.graphite }}>
        <video
          ref={scrollVideoRef}
          src="/scroll_video.mp4"
          muted playsInline preload="auto"
          style={{
            width: '100%', height: '100%', objectFit: 'cover',
            filter: 'brightness(0.26) contrast(1.1) saturate(0.35)',
          }}
        />
        {/* Vignette. (The previous build shipped a malformed gradient value
            here, so this layer rendered as nothing at all.) */}
        <div style={{
          position: 'absolute', inset: 0,
          background: 'radial-gradient(ellipse 90% 70% at 50% 45%, rgba(21,23,27,0.20) 0%, rgba(21,23,27,0.88) 100%)',
        }} />
      </div>

      {/* Covariance grid — the brand motif as a faint fixed overlay */}
      <div aria-hidden="true" style={{
        position: 'fixed', inset: 0, zIndex: 2, pointerEvents: 'none',
        backgroundImage: `linear-gradient(${C.ash}0A 1px, transparent 1px),
                          linear-gradient(90deg, ${C.ash}0A 1px, transparent 1px)`,
        backgroundSize: '72px 72px',
      }} />

      {/* ── NAV ──────────────────────────────────────────────────────────── */}
      <header style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: navSolid ? '14px 40px' : '22px 40px',
        // A solid scrim, not a blur. Glass effects are out of system here.
        background: navSolid ? 'rgba(21,23,27,0.94)' : 'transparent',
        borderBottom: `1px solid ${navSolid ? 'rgba(201,195,185,0.16)' : 'transparent'}`,
        transition: 'all 380ms cubic-bezier(0.22,1,0.36,1)',
      }}>
        <a href="#returns" style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'inherit' }}>
          <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
            <ellipse cx="12" cy="12" rx="10.5" ry="6.5" fill="none" stroke="rgba(201,195,185,0.45)" strokeWidth="1" />
            <ellipse cx="12" cy="12" rx="6" ry="3.6" fill="none" stroke="rgba(201,195,185,0.75)" strokeWidth="1" />
            <circle cx="12" cy="12" r="2.4" fill={C.vermillion} />
          </svg>
          <span style={{ fontFamily: HEAD, fontSize: 16, fontWeight: 700, letterSpacing: '-0.02em', color: C.bone }}>
            ReturnIQ
          </span>
        </a>

        {/* The nav IS the story — five stages, in order. */}
        <nav className="hide-mobile" style={{ display: 'flex', gap: 26 }}>
          {STAGES.map(s => (
            <a key={s.id} href={`#${s.id}`} className="hover-rule" style={{
              fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em',
              textTransform: 'uppercase', color: C.onDarkMuted, transition: 'color 150ms',
            }}
              onMouseEnter={e => { e.currentTarget.style.color = C.bone }}
              onMouseLeave={e => { e.currentTarget.style.color = C.onDarkMuted }}
            >{s.name}</a>
          ))}
        </nav>

        <button onClick={() => navigate('/login')} style={{
          background: C.vermillion, color: '#fff', padding: '9px 20px',
          fontSize: 13, fontWeight: 500, borderRadius: 5, transition: 'background 150ms',
        }}
          onMouseEnter={e => { e.currentTarget.style.background = '#B93A18' }}
          onMouseLeave={e => { e.currentTarget.style.background = C.vermillion }}
        >
          Sign in
        </button>
      </header>

      {/* ── SCROLL PROGRESS — the estimate converging, top edge ──────────── */}
      <div style={{ position: 'fixed', top: 0, left: 0, right: 0, height: 2, zIndex: 101, background: 'transparent' }}>
        <div style={{ width: `${progress * 100}%`, height: '100%', background: C.vermillion, transition: 'width 90ms linear' }} />
      </div>

      {/* ═══════════════════════════════════════════════════════════════════
          CONTENT — every section floats above the fixed video
          ═══════════════════════════════════════════════════════════════ */}
      <div style={{ position: 'relative', zIndex: 3 }}>

        {/* ── 01 · RETURNS ─────────────────────────────────────────────────
            The thesis. A return is not a parcel — it is a noisy reading. */}
        <section id="returns" className="section section--tall" style={{ paddingTop: 140 }}>
          <div className="section__inner">
            <div className="eyebrow" style={{ color: C.vermillion, marginBottom: 26 }}>
              01 — Returns
            </div>

            <h1 style={{
              fontFamily: HEAD, fontSize: 'clamp(44px, 7.4vw, 96px)', fontWeight: 700,
              lineHeight: 0.98, letterSpacing: '-0.04em', color: C.bone, marginBottom: 32,
              maxWidth: 15 + 'ch',
            }}>
              Every return is<br />a noisy reading.
            </h1>

            <div style={{ display: 'flex', gap: 40, flexWrap: 'wrap', alignItems: 'flex-start' }}>
              <p style={{
                fontSize: 18, lineHeight: 1.65, color: C.onDarkMuted,
                maxWidth: '46ch', flex: '1 1 380px',
              }}>
                One customer changed their mind. One item never fit. One order was
                never going to be kept. From the outside they look identical — and
                that is precisely the problem worth solving.
              </p>

              <div style={{ flex: '0 1 300px', borderLeft: `1px solid rgba(201,195,185,0.22)`, paddingLeft: 24 }}>
                <p style={{ fontSize: 14, lineHeight: 1.7, color: C.onDarkMuted, marginBottom: 20 }}>
                  ReturnIQ separates the signal from the noise on every one, before
                  you have spent a rupee moving it.
                </p>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <button onClick={() => navigate('/register')} style={{
                    background: C.vermillion, color: '#fff', padding: '13px 26px',
                    fontSize: 14, fontWeight: 500, borderRadius: 5, transition: 'background 150ms',
                  }}
                    onMouseEnter={e => { e.currentTarget.style.background = '#B93A18' }}
                    onMouseLeave={e => { e.currentTarget.style.background = C.vermillion }}
                  >
                    Start free
                  </button>
                  <button onClick={() => navigate('/login')} style={{
                    background: 'transparent', color: C.bone, padding: '13px 26px',
                    fontSize: 14, fontWeight: 500, borderRadius: 5,
                    border: `1px solid rgba(201,195,185,0.34)`, transition: 'all 150ms',
                  }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = C.ash; e.currentTarget.style.background = 'rgba(237,233,227,0.06)' }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(201,195,185,0.34)'; e.currentTarget.style.background = 'transparent' }}
                  >
                    See the dashboard
                  </button>
                </div>
              </div>
            </div>

            {/* The pipeline, stated once, plainly. */}
            <div style={{ marginTop: 72, borderTop: `1px solid rgba(201,195,185,0.18)`, paddingTop: 20 }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 0 }}>
                {STAGES.map((s, i) => (
                  <div key={s.id} style={{
                    flex: '1 1 150px', padding: '4px 18px 0',
                    borderLeft: i === 0 ? 'none' : `1px solid rgba(201,195,185,0.18)`,
                  }}>
                    <div style={{ fontFamily: MONO, fontSize: 10, color: i === 4 ? C.vermillion : C.iron, letterSpacing: '0.1em', marginBottom: 6 }}>
                      {s.n}
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 500, color: C.bone, marginBottom: 2 }}>{s.name}</div>
                    <div style={{ fontSize: 12, color: C.onDarkMuted, lineHeight: 1.5 }}>{s.gloss}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ── 02 · SIGNAL ──────────────────────────────────────────────────
            The signature moment: the noisy series resolving into an
            estimate, drawn live. This is the one bold element on the page. */}
        <section id="signal" className="section section--tall">
          <div className="section__inner" data-reveal="signal" style={revealed('signal')}>
            <div className="eyebrow" style={{ color: C.vermillion, marginBottom: 22 }}>02 — Signal</div>
            <h2 style={{
              fontFamily: HEAD, fontSize: 'clamp(30px, 4.4vw, 54px)', fontWeight: 700,
              letterSpacing: '-0.03em', lineHeight: 1.05, color: C.bone, marginBottom: 18, maxWidth: '18ch',
            }}>
              The estimate is already there. It is buried.
            </h2>
            <p style={{ fontSize: 16, lineHeight: 1.65, color: C.onDarkMuted, maxWidth: '54ch', marginBottom: 46 }}>
              Grey is what your returns table shows you: raw, unresolved, every row
              looking as urgent as every other. Vermillion is what the model has
              already worked out.
            </p>

            <ConvergencePlot visible={!!vis.signal} />

            <div style={{ display: 'flex', gap: 28, marginTop: 26, flexWrap: 'wrap' }}>
              {[
                { swatch: C.iron, label: 'Raw input', note: 'what a return looks like on arrival' },
                { swatch: C.vermillion, label: 'Resolved estimate', note: 'what it costs, and what to do' },
              ].map(l => (
                <div key={l.label} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <span style={{ width: 10, height: 10, background: l.swatch, marginTop: 5, flexShrink: 0 }} />
                  <div>
                    <div style={{ fontSize: 13, color: C.bone, fontWeight: 500 }}>{l.label}</div>
                    <div style={{ fontSize: 12, color: C.onDarkMuted }}>{l.note}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── 03 · INTELLIGENCE ────────────────────────────────────────────
            What the models actually produce. Six capabilities, set as a
            ruled table rather than six cards — this is a specification. */}
        <section id="intelligence" className="section">
          <div className="section__inner" data-reveal="intel" style={revealed('intel')}>
            <div className="eyebrow" style={{ color: C.vermillion, marginBottom: 22 }}>03 — Intelligence</div>
            <h2 style={{
              fontFamily: HEAD, fontSize: 'clamp(30px, 4.4vw, 54px)', fontWeight: 700,
              letterSpacing: '-0.03em', lineHeight: 1.05, color: C.bone, marginBottom: 46, maxWidth: '20ch',
            }}>
              Five models, one pass, ten milliseconds.
            </h2>

            <div style={{ borderTop: `1px solid rgba(201,195,185,0.22)` }}>
              {[
                { k: 'Cost',       q: 'What will this return actually cost me?', a: 'A rupee figure per return, not a category average. Gradient-boosted on 80,000 historical returns.' },
                { k: 'Fraud',      q: 'Is this customer working the policy?',    a: 'Return rate, payment mode, stated reason, seasonality and value pattern, scored together rather than as separate rules.' },
                { k: 'Condition',  q: 'What will come back, and in what state?', a: 'Damage probability before pickup, so the item is routed to the right place the first time.' },
                { k: 'Resale',     q: 'What is it still worth?',                 a: 'Recoverable value by condition and category — the number that decides resell, refurbish, or write off.' },
                { k: 'Carbon',     q: 'What did the movement cost the planet?',  a: 'CO₂ per return and per courier, with the greener routing alternative surfaced alongside it.' },
                { k: 'Routing',    q: 'So what do I do?',                        a: 'Accept, reject, refund and keep, or charge a fee. One decision, with the confidence attached.' },
              ].map((row, i) => (
                <div key={row.k} className="hover-lift" style={{
                  display: 'grid', gridTemplateColumns: '110px minmax(0,1fr) minmax(0,1.25fr)',
                  gap: 24, padding: '22px 0',
                  borderBottom: `1px solid rgba(201,195,185,0.22)`,
                  ...revealed('intel', 60 + i * 50),
                }}>
                  <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: '0.1em', color: C.vermillion, textTransform: 'uppercase' }}>
                    {row.k}
                  </div>
                  <div style={{ fontFamily: HEAD, fontSize: 17, fontWeight: 500, color: C.bone, letterSpacing: '-0.015em', lineHeight: 1.3 }}>
                    {row.q}
                  </div>
                  <div style={{ fontSize: 13.5, color: C.onDarkMuted, lineHeight: 1.65 }}>
                    {row.a}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── AMBIENT BAND ─────────────────────────────────────────────────
            The looping video, kept, but demoted to a quiet horizontal band
            between two arguments. No claims layered over it. */}
        <section style={{ position: 'relative', overflow: 'hidden' }}>
          <div data-reveal="band" style={{ ...revealed('band'), position: 'relative', height: 300 }}>
            <video
              ref={truckVideoRef}
              src="/truck_video.mp4"
              muted loop playsInline
              style={{ width: '100%', height: '100%', objectFit: 'cover', filter: 'brightness(0.3) contrast(1.1) saturate(0.3)' }}
            />
            <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(90deg, ${C.graphite} 0%, rgba(21,23,27,0.5) 35%, rgba(21,23,27,0.5) 65%, ${C.graphite} 100%)` }} />
            <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(180deg, ${C.graphite} 0%, transparent 26%, transparent 74%, ${C.graphite} 100%)` }} />
            <div style={{
              position: 'absolute', inset: 0, display: 'flex',
              alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: 24,
            }}>
              <p style={{
                fontFamily: HEAD, fontSize: 'clamp(20px, 2.6vw, 32px)', fontWeight: 500,
                letterSpacing: '-0.025em', color: C.bone, lineHeight: 1.3, maxWidth: '22ch',
              }}>
                The cheapest return is the one you never move.
              </p>
            </div>
          </div>
        </section>

        {/* ── 04 · DECISION ────────────────────────────────────────────────
            One return, resolved. Real output shape, terminal-set. */}
        <section id="decision" className="section section--tall">
          <div className="section__inner" data-reveal="decision" style={revealed('decision')}>
            <div className="eyebrow" style={{ color: C.vermillion, marginBottom: 22 }}>04 — Decision</div>
            <h2 style={{
              fontFamily: HEAD, fontSize: 'clamp(30px, 4.4vw, 54px)', fontWeight: 700,
              letterSpacing: '-0.03em', lineHeight: 1.05, color: C.bone, marginBottom: 18, maxWidth: '18ch',
            }}>
              An answer, not a dashboard to interpret.
            </h2>
            <p style={{ fontSize: 16, lineHeight: 1.65, color: C.onDarkMuted, maxWidth: '52ch', marginBottom: 40 }}>
              Every scored return resolves to one of four actions, with the reasoning
              attached. Your team acts on the decision; they do not reverse-engineer it.
            </p>

            <div style={{
              background: 'rgba(21,23,27,0.72)',
              border: `1px solid rgba(201,195,185,0.22)`,
              borderLeft: `2px solid ${C.vermillion}`,
              borderRadius: 6, padding: '26px 30px',
              fontFamily: MONO, fontSize: 12.5, lineHeight: 2.05,
            }}>
              <div style={{ color: C.iron, marginBottom: 10 }}>$ returniq score --order ORD-10482</div>
              {[
                ['order', 'ORD-10482', C.onDark],
                ['predicted_cost', '₹487.32', C.vermillionLift],
                ['risk', '18.4 / 100', '#6F9E6A'],
                ['fraud', '12.0 / 100', '#6F9E6A'],
                ['resale_value', '₹1,240', C.onDark],
                ['carbon', '1.84 kg CO₂', C.onDark],
                ['confidence', '96.8%', C.onDark],
                ['latency', '7.2 ms', C.iron],
              ].map(([k, v, col]) => (
                <div key={k} style={{ display: 'flex', gap: 12 }}>
                  <span style={{ color: C.vermillion }}>›</span>
                  <span style={{ color: C.onDarkMuted, minWidth: 150 }}>{k}</span>
                  <span style={{ color: col }}>{v}</span>
                </div>
              ))}
              <div style={{
                marginTop: 16, paddingTop: 14, borderTop: `1px solid rgba(201,195,185,0.2)`,
                display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
              }}>
                <span style={{ color: C.onDarkMuted }}>decision</span>
                <span style={{
                  background: C.vermillion, color: '#fff', padding: '3px 12px',
                  borderRadius: 3, fontSize: 12, letterSpacing: '0.06em',
                }}>
                  ACCEPT
                </span>
                <span style={{ color: C.iron, fontSize: 11.5 }}>refund queued · pickup scheduled</span>
              </div>
            </div>
          </div>
        </section>

        {/* ── 05 · RECOVERY ────────────────────────────────────────────────
            Close on the outcome and the single ask. */}
        <section id="recovery" className="section section--tall">
          <div className="section__inner" data-reveal="recovery" style={revealed('recovery')}>
            <div className="eyebrow" style={{ color: C.vermillion, marginBottom: 22 }}>05 — Recovery</div>

            <h2 style={{
              fontFamily: HEAD, fontSize: 'clamp(32px, 5vw, 62px)', fontWeight: 700,
              letterSpacing: '-0.035em', lineHeight: 1.02, color: C.bone, marginBottom: 44, maxWidth: '16ch',
            }}>
              Returns stop being a leak.
            </h2>

            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              borderTop: `1px solid rgba(201,195,185,0.22)`,
              borderBottom: `1px solid rgba(201,195,185,0.22)`,
              marginBottom: 46,
            }}>
              {[
                { v: '80,000', l: 'returns behind the model', s: 'training set' },
                { v: '0.999', l: 'cost prediction R²', s: 'held-out score' },
                { v: '< 10ms', l: 'to a decision', s: 'per request' },
                { v: '5', l: 'models per pass', s: 'run in parallel' },
              ].map((m, i) => (
                <div key={m.l} style={{
                  padding: '26px 22px',
                  borderLeft: i === 0 ? 'none' : `1px solid rgba(201,195,185,0.22)`,
                }}>
                  <div style={{
                    fontFamily: MONO, fontSize: 'clamp(22px, 2.6vw, 32px)', fontWeight: 500,
                    color: C.bone, letterSpacing: '-0.04em', marginBottom: 10,
                  }}>
                    {m.v}
                  </div>
                  <div style={{ fontSize: 13, color: C.onDark, marginBottom: 2 }}>{m.l}</div>
                  <div style={{ fontSize: 11.5, color: C.iron, fontFamily: MONO, letterSpacing: '0.04em' }}>{m.s}</div>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap', alignItems: 'center' }}>
              <button onClick={() => navigate('/register')} style={{
                background: C.vermillion, color: '#fff', padding: '15px 34px',
                fontSize: 15, fontWeight: 500, borderRadius: 5, transition: 'background 150ms',
              }}
                onMouseEnter={e => { e.currentTarget.style.background = '#B93A18' }}
                onMouseLeave={e => { e.currentTarget.style.background = C.vermillion }}
              >
                Create an account
              </button>
              <p style={{ fontSize: 13.5, color: C.onDarkMuted, maxWidth: '34ch', lineHeight: 1.6 }}>
                Free to start, no card. Score your first return in the browser before
                you connect anything.
              </p>
            </div>
          </div>
        </section>
      </div>

      {/* ── FOOTER ─────────────────────────────────────────────────────────── */}
      <footer style={{
        position: 'relative', zIndex: 3,
        background: C.graphite, borderTop: `1px solid rgba(201,195,185,0.18)`,
        padding: '26px 40px', display: 'flex', justifyContent: 'space-between',
        alignItems: 'center', flexWrap: 'wrap', gap: 16,
      }}>
        <div style={{ fontFamily: MONO, fontSize: 10.5, color: C.iron, letterSpacing: '0.08em' }}>
          © 2026 ReturnIQ — signal over noise
        </div>
        <div style={{ display: 'flex', gap: 22 }}>
          {['Privacy', 'Terms', 'API docs', 'Status'].map(l => (
            <span key={l} style={{
              fontFamily: MONO, fontSize: 10.5, color: C.iron, cursor: 'pointer',
              letterSpacing: '0.08em', transition: 'color 150ms',
            }}
              onMouseEnter={e => { e.currentTarget.style.color = C.bone }}
              onMouseLeave={e => { e.currentTarget.style.color = C.iron }}
            >{l}</span>
          ))}
        </div>
      </footer>
    </div>
  )
}

/* ── ConvergencePlot ──────────────────────────────────────────────────────
   The signature element. A noisy measurement series in Iron, and the
   filtered estimate in Vermillion drawing itself across on reveal.

   The data is generated once with a fixed seed so the shape is stable
   between renders — a chart that reshuffles on every scroll would read as
   decoration. Pure SVG, no chart library, no dependency. */
function ConvergencePlot({ visible }) {
  const W = 1000, H = 260
  const { noisePath, signalPath, band } = React.useMemo(() => {
    // Deterministic pseudo-random — same curve every load.
    let seed = 42
    const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648 }

    const N = 84
    const truth = i => H * 0.62 - Math.sin(i / 11) * 42 - (i / N) * 46

    const noise = []
    const est = []
    let e = H * 0.30           // the estimate starts badly wrong…
    let gain = 0.42            // …with a high gain that decays as it settles

    for (let i = 0; i < N; i++) {
      const t = truth(i)
      const m = t + (rnd() - 0.5) * 84
      noise.push([(i / (N - 1)) * W, m])
      e = e + gain * (m - e)
      gain = Math.max(0.055, gain * 0.955)
      est.push([(i / (N - 1)) * W, e])
    }

    const line = pts => pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')

    // Uncertainty band: wide at the start, tightening onto the estimate.
    const spread = i => 46 * Math.pow(1 - i / (N - 1), 1.6) + 5
    const top = est.map(([x, y], i) => [x, y - spread(i)])
    const bot = est.map(([x, y], i) => [x, y + spread(i)]).reverse()

    // The band is one closed shape: along the upper edge, then back along
    // the lower edge. `line(bot)` starts with an M, which would break the
    // fill — swap it for an L so the two edges join into a single path.
    return {
      noisePath: line(noise),
      signalPath: line(est),
      band: `${line(top)} L${line(bot).slice(1)} Z`,
    }
  }, [])

  return (
    <div style={{
      border: '1px solid rgba(201,195,185,0.22)', borderRadius: 6,
      background: 'rgba(21,23,27,0.55)', padding: '20px 22px 14px',
    }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', overflow: 'visible' }} role="img"
        aria-label="A noisy measurement series resolving into a single smooth estimate">
        {/* Grid — structure, barely there */}
        {[0.25, 0.5, 0.75].map(f => (
          <line key={f} x1="0" x2={W} y1={H * f} y2={H * f} stroke="rgba(201,195,185,0.10)" strokeWidth="1" />
        ))}

        {/* Uncertainty band, tightening left to right */}
        <path d={band} fill="rgba(222,75,34,0.09)" style={{
          opacity: visible ? 1 : 0, transition: 'opacity 900ms 500ms ease-out',
        }} />

        {/* Raw measurements — noise */}
        <path d={noisePath} fill="none" stroke={C.iron} strokeWidth="1.25" strokeOpacity="0.85"
          strokeLinejoin="round" style={{
            opacity: visible ? 1 : 0, transition: 'opacity 700ms ease-out',
          }} />

        {/* The estimate — signal. Drawn on, once. */}
        <path d={signalPath} fill="none" stroke={C.vermillion} strokeWidth="2.25"
          strokeLinecap="round" strokeLinejoin="round"
          pathLength="1"
          style={{
            strokeDasharray: 1,
            strokeDashoffset: visible ? 0 : 1,
            transition: 'stroke-dashoffset 1900ms cubic-bezier(0.16,1,0.3,1) 320ms',
          }} />
      </svg>

      <div style={{
        display: 'flex', justifyContent: 'space-between',
        fontFamily: MONO, fontSize: 10, color: C.iron,
        letterSpacing: '0.1em', marginTop: 8, textTransform: 'uppercase',
      }}>
        <span>return arrives</span>
        <span style={{ color: C.vermillion }}>decision issued</span>
      </div>
    </div>
  )
}
