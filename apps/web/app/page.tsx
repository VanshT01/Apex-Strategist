import Link from "next/link";

export default function Home() {
  return (
    <main className="home-shell">
      <section className="hero-grid">
        <div className="hero-copy">
          <p className="eyebrow mt-0">Formula 1 strategy simulator</p>
          <h1>
            ANALYZE PAST RACES.
            <br />
            <em>THEN CHANGE THEM.</em>
          </h1>
          <p className="hero-description">
            Every lap, strategy, tyre and weather shift reconstructed into an F1
            pit wall you can study or take over.
          </p>
          <div className="hero-actions">
            <Link href="/engineer" className="f1-button f1-button--primary">
              <span>Enter Race Engineer</span>
              <b aria-hidden>→</b>
            </Link>
            <Link href="/analyze" className="f1-button f1-button--ghost">
              Analyze past races
            </Link>
          </div>
          <div className="hero-stats" aria-label="Application coverage">
            <div>
              <strong>114</strong>
              <span>GRANDS PRIX</span>
            </div>
            <div>
              <strong>125K</strong>
              <span>RACE LAPS</span>
            </div>
            <div>
              <strong>5</strong>
              <span>SEASONS</span>
            </div>
          </div>
        </div>

        <div className="race-blueprint" aria-label="Circuit strategy preview">
          <div className="race-blueprint__head">
            <div>
              <span>RACE MODEL / SILVERSTONE</span>
              <strong>STRATEGY WINDOW</strong>
            </div>
            <span className="blueprint-lap">LAP 18 / 52</span>
          </div>
          <div className="circuit-plot">
            <svg
              viewBox="0 0 720 430"
              role="img"
              aria-label="Technical circuit outline divided into three sectors"
            >
              <defs>
                <linearGradient id="track-glow" x1="0" x2="1">
                  <stop offset="0" stopColor="#8d929b" />
                  <stop offset="0.55" stopColor="#ffffff" />
                  <stop offset="1" stopColor="#ff1801" />
                </linearGradient>
              </defs>
              <path
                className="circuit-gridline"
                d="M34 94H686M34 214H686M34 334H686M150 34V396M360 34V396M570 34V396"
              />
              <path
                className="circuit-shadow"
                d="M134 287C101 247 98 194 132 154C169 110 235 105 274 136C308 163 329 156 362 119C392 85 450 76 494 102C534 126 554 172 542 213C530 255 549 285 591 304C625 320 638 355 616 374C587 399 536 376 501 351C466 326 428 322 384 343C335 366 283 362 252 331C224 304 195 304 169 312C154 316 143 305 134 287Z"
              />
              <path
                className="circuit-line"
                d="M134 287C101 247 98 194 132 154C169 110 235 105 274 136C308 163 329 156 362 119C392 85 450 76 494 102C534 126 554 172 542 213C530 255 549 285 591 304C625 320 638 355 616 374C587 399 536 376 501 351C466 326 428 322 384 343C335 366 283 362 252 331C224 304 195 304 169 312C154 316 143 305 134 287Z"
              />
              <g className="circuit-marker circuit-marker--one">
                <circle cx="137" cy="150" r="7" />
                <text x="152" y="146">
                  S1
                </text>
              </g>
              <g className="circuit-marker circuit-marker--two">
                <circle cx="496" cy="103" r="7" />
                <text x="511" y="99">
                  S2
                </text>
              </g>
              <g className="circuit-marker circuit-marker--three">
                <circle cx="502" cy="351" r="7" />
                <text x="517" y="347">
                  S3
                </text>
              </g>
              <g className="car-marker">
                <circle cx="251" cy="331" r="14" />
                <circle cx="251" cy="331" r="4" />
                <text x="274" y="336">
                  VER · P2
                </text>
              </g>
            </svg>
            <div className="plot-readout plot-readout--top">
              <span>GAP AHEAD</span>
              <strong>+2.148s</strong>
            </div>
            <div className="plot-readout plot-readout--bottom">
              <span>TRACK</span>
              <strong>34.8°C</strong>
            </div>
          </div>
          <div className="strategy-strip">
            <div>
              <span>ACTIVE TYRE</span>
              <strong>
                <i className="medium-indicator" /> MEDIUM · 18 LAPS
              </strong>
            </div>
            <div>
              <span>OPTIMAL WINDOW</span>
              <strong>LAP 20 TO 23</strong>
            </div>
            <div>
              <span>PROJECTED REJOIN</span>
              <strong>P4 · CLEAR AIR</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="mode-grid" aria-label="Choose an experience">
        <Link href="/analyze" className="experience-card">
          <span className="experience-card__number">01</span>
          <div>
            <p className="eyebrow">Race archive</p>
            <h2>ANALYZE THE PAST</h2>
            <p>
              Replay recorded races lap by lap with synchronized timing,
              weather, tyres, stints and race control.
            </p>
          </div>
          <b aria-hidden>↗</b>
        </Link>
        <Link href="/engineer" className="experience-card experience-card--red">
          <span className="experience-card__number">02</span>
          <div>
            <p className="eyebrow">Pit wall simulator</p>
            <h2>ENGINEER THE RACE</h2>
            <p>
              Own every pit call from lap 1 and carry your independent strategy
              to the chequered flag.
            </p>
          </div>
          <b aria-hidden>↗</b>
        </Link>
      </section>

      <footer className="home-footer">
        <span>BUILT BY</span>
        <a href="https://github.com/VanshT01" target="_blank" rel="noreferrer">
          VANSH TALREJA <b aria-hidden>↗</b>
        </a>
      </footer>
    </main>
  );
}
