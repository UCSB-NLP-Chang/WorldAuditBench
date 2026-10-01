import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import data from "../content.json";
import { RadialTaxonomy } from "./taxonomy";
import "./style.css";
const REPO = "https://github.com/UCSB-NLP-Chang/WorldAuditBench";
const PAPER = "https://arxiv.org/pdf/2609.40325";
const authors = [
  ["Ziyan Jiang", "1,*", "https://xmhzz2018.github.io/"],
  ["Jingbo Yang", "1,*", "https://kimperyang.github.io/"],
  ["Jiabao Ji", "1,*", "https://question406.github.io/"],
  ["Yujian Liu", "1", "https://yujianll.github.io/"],
  ["Qiucheng Wu", "1", "https://wuqiuche.github.io/"],
  ["Tommi Jaakkola", "2", "https://people.csail.mit.edu/tommi/"],
  ["Yang Zhang", "3", "https://mitibm.mit.edu/people/yang-zhang/"],
  ["Shiyu Chang", "1", "https://code-terminator.github.io/"],
];
const scores = [
  {
    name: "GPT-6 Astra",
    logo: "openai",
    vlm: [59.3, 29.3, 45.1, 12.5, 68.2, 42.3, 2.955],
    vla: [20.3, 17.1, 25.5, 0, 13.6, 16.4, 0.281],
  },
  {
    name: "Gemini 3.8 Flash",
    logo: "gemini-color",
    vlm: [49.2, 22, 29.4, 12.5, 50, 32.4, 1.382],
    vla: [20.3, 24.4, 17.6, 5, 18.2, 17.4, 0.296],
  },
  {
    name: "Claude Opus 5",
    logo: "anthropic",
    vlm: [35.6, 19.5, 29.4, 12.5, 50, 28.2, 2.445],
    vla: [22, 22, 11.8, 2.5, 13.6, 15, 0.727],
  },
  {
    name: "Muse Spark 1.3",
    logo: "meta-color",
    vlm: [22, 12.2, 13.7, 5, 22.7, 15, 0.791],
    vla: [5.1, 9.8, 9.8, 0, 9.1, 6.6, 0.112],
  },
  {
    name: "Qwen 3.8 Flash",
    logo: "qwen-color",
    vlm: [11.9, 7.3, 3.9, 2.5, 22.7, 8.5, 0.077],
    vla: [18.6, 22, 11.8, 0, 4.5, 12.7, 0.039],
  },
];
const bib = `@misc{jiang2026worldauditbench,
  title  = {WorldAuditBench: Interactive 3D World Auditing
            with Multimodal Agents},
  author = {Ziyan Jiang and Jingbo Yang and Jiabao Ji and
            Yujian Liu and Qiucheng Wu and Tommi Jaakkola and
            Yang Zhang and Shiyu Chang},
  year   = {2026},
  eprint = {2609.40325},
  archivePrefix = {arXiv},
  primaryClass = {cs.AI},
  url    = {https://arxiv.org/abs/2609.40325}
}`;
function Icon({ name, size = 18, ...props }) {
  const paths = {
    arrow: (
      <>
        <path d="M5 12h14M12 5l7 7-7 7" />
      </>
    ),
    external: (
      <>
        <path d="M14 3h7v7M21 3l-9 9" />
        <path d="M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5" />
      </>
    ),
    paper: (
      <>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h5" />
      </>
    ),
    code: (
      <>
        <path d="m8 5-7 7 7 7M16 5l7 7-7 7M14 3l-4 18" />
      </>
    ),
    play: <path d="m8 4 12 8-12 8z" />,
    pause: (
      <>
        <path d="M8 4v16M16 4v16" />
      </>
    ),
    copy: (
      <>
        <rect x="8" y="8" width="12" height="13" rx="2" />
        <path d="M16 8V3H3v13h5" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    expand: <path d="M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5" />,
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    globe: (
      <>
        <circle cx="12" cy="12" r="9" />
        <ellipse cx="12" cy="12" rx="4" ry="9" />
        <path d="M3 12h18" />
      </>
    ),
    down: <path d="m6 9 6 6 6-6" />,
    search: (
      <>
        <circle cx="10" cy="10" r="7" />
        <path d="m15 15 6 6" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {paths[name] || paths.arrow}
    </svg>
  );
}
function BrandIcon({ name }) {
  return (
    <img
      className="brand-icon"
      src={`./media/${name}.svg`}
      alt=""
      aria-hidden="true"
    />
  );
}
function Mark() {
  return <img className="mark" src="./media/worldaudit-logo.png" alt="" />;
}
function Label({ children, light = false }) {
  return (
    <p className={`eyebrow ${light ? "on-dark" : ""}`}>
      <span />
      {children}
    </p>
  );
}
function Header() {
  const [open, setOpen] = useState(false);
  return (
    <header className="site-header">
      <div className="nav-inner">
        <a className="brand" href="#top" aria-label="WorldAuditBench home">
          <Mark />
          <span>
            WorldAudit<span>Bench</span>
          </span>
        </a>
        <nav className={open ? "is-open" : ""} aria-label="Main navigation">
          {[
            ["Overview", "overview"],
            ["Explore", "explore"],
            ["Results", "results"],
            ["Environments", "environments"],
          ].map(([name, id]) => (
            <a key={id} href={"#" + id} onClick={() => setOpen(false)}>
              {name}
            </a>
          ))}
        </nav>
        <button
          className="menu-toggle icon-button"
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          <Icon name={open ? "close" : "menu"} />
        </button>
      </div>
    </header>
  );
}
function Hero() {
  const [scene, setScene] = useState("G1"),
    [playing, setPlaying] = useState(false);
  const video = useRef(null);
  const item = data.examples.find((x) => x.id === scene);
  useEffect(() => {
    setPlaying(false);
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries[0].isIntersecting) video.current?.pause();
      },
      { threshold: 0.1 },
    );
    if (video.current) observer.observe(video.current);
    return () => observer.disconnect();
  }, [scene]);
  const clips = [
    ["G1", "Floating objects"],
    ["C1", "Invisible boundaries"],
    ["T1", "Changing worlds"],
  ];
  return (
    <section className="hero" id="top">
      <div className="hero-grid" aria-hidden="true" />
      <div className="hero-glow" aria-hidden="true" />
      <div className="wrap hero-inner">
        <h1 className="paper-title">
          <span className="title-line">
            <Mark />
            <span className="title-name">WorldAuditBench</span>:
          </span>
          <span className="title-line">Interactive 3D World Auditing</span>
          <span className="title-line">with Multimodal Agents</span>
        </h1>
        <p className="hero-description">
          A benchmark for discovering and explaining anomalies across 213 tasks
          in 13 interactive 3D environments.
        </p>
        <div className="authors">
          {authors.map(([name, aff, url]) => (
            <span key={name}>
              <a href={url} target="_blank" rel="noreferrer">
                {name}
              </a>
              <sup>{aff}</sup>
            </span>
          ))}
        </div>
        <div className="affiliations">
          <span>
            <sup>1</sup> UC Santa Barbara
          </span>
          <span>
            <sup>2</sup> MIT CSAIL
          </span>
          <span>
            <sup>3</sup> MIT-IBM Watson AI Lab
          </span>
        </div>
        <p className="equal">* Equal contribution</p>
        <div className="hero-actions">
          <a
            className="button primary"
            href={PAPER}
            target="_blank"
            rel="noreferrer"
          >
            <Icon name="paper" />
            Paper
          </a>
          <a
            className="button secondary"
            href={REPO}
            target="_blank"
            rel="noreferrer"
          >
            <BrandIcon name="github" />
            Code
          </a>
          <button
            className="button secondary dataset-button"
            type="button"
            aria-disabled="true"
            aria-label="Dataset (coming soon on Hugging Face)"
            title="Coming soon on Hugging Face"
          >
            <BrandIcon name="huggingface" />
            Dataset
          </button>
          <a className="button secondary" href="#explore">
            <Icon name="play" />
            Demo
          </a>
        </div>
        <div className="hero-showcase">
          <div className="showcase-toolbar">
            <div>
              <span className="record-dot" /> INSIDE THE BENCHMARK
            </div>
            <span>Real environments. Recorded demonstrations.</span>
            <button
              className="showcase-fullscreen"
              aria-label="View demonstration fullscreen"
              onClick={() => {
                const v = video.current;
                if (v.requestFullscreen) v.requestFullscreen().catch(() => {});
                else if (v.webkitEnterFullscreen) v.webkitEnterFullscreen();
              }}
            >
              <Icon name="expand" size={15} />
            </button>
          </div>
          <div className="showcase-body">
            <div className="hero-video">
              <video
                ref={video}
                key={scene}
                controls={playing}
                playsInline
                muted
                loop
                preload="none"
                poster={"./" + item.frames[0].src}
                onPlay={() => setPlaying(true)}
                onPause={() => setPlaying(false)}
                aria-label={item.title}
              >
                <source
                  src={
                    scene === "G1"
                      ? "./assets/hero-loop.mp4"
                      : "./" + item.video
                  }
                  type="video/mp4"
                />
              </video>
              {!playing && (
                <button
                  className="hero-play"
                  onClick={() => video.current.play().catch(() => {})}
                  aria-label={`Play ${item.title} demonstration`}
                >
                  <Icon name="play" size={25} />
                  <span>Watch the anomaly</span>
                </button>
              )}
              <span className="video-corner">
                {scene} <span>/</span>{" "}
                {data.families.find((f) => f.id === item.family).name}
              </span>
            </div>
            <div className="showcase-aside">
              <Label light>LOOK CLOSER</Label>
              <h3>
                A convincing world. <br />
                An unexpected flaw.
              </h3>
              <p>{item.evidence}</p>
              <div
                className="scene-select"
                aria-label="Featured demonstrations"
              >
                {clips.map(([id, name], i) => (
                  <button
                    key={id}
                    onClick={() => setScene(id)}
                    className={id === scene ? "active" : ""}
                    aria-pressed={id === scene}
                  >
                    <span>0{i + 1}</span>
                    {name}
                    <Icon name="arrow" size={15} />
                  </button>
                ))}
              </div>
              <a href="#explore" className="all-demos">
                Explore all 15 anomaly types <Icon name="arrow" size={15} />
              </a>
            </div>
          </div>
        </div>
        <div className="stat-strip">
          {[
            ["213", "Anomaly tasks"],
            ["13", "Interactive environments"],
            ["5", "Anomaly families"],
            ["15", "Anomaly types"],
            ["2", "Auditing paradigms"],
          ].map(([n, label]) => (
            <div key={label}>
              <strong>{n}</strong>
              <span>{label}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
function Overview() {
  return (
    <section id="overview" className="section wrap overview">
      <div>
        <Label>THE QUESTION</Label>
        <h2 className="section-title">
          Worlds can look right.
          <br />
          <span>Do they behave right?</span>
        </h2>
      </div>
      <div className="overview-copy">
        <p>
          Multimodal agents can navigate a scene. But can they notice a floating
          chair, test a wall’s collision, or recognize an object that disappears
          after they look away?
        </p>
        <p>
          <strong>WorldAuditBench</strong> turns these questions into 213 tasks
          across Unreal Engine 5 and Three.js. Auditing requires agents to
          connect what they see with what they do: explore a world, investigate
          a hypothesis, and report an anomaly with evidence.
        </p>
        <div className="takeaway">
          <span className="takeaway-number">
            42.3<span>%</span>
          </span>
          <div>
            <strong>The strongest agent still trails humans.</strong>
            <p>
              Best agent success rate, compared with <b>83.4%</b> for humans.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
function Explorer() {
  const [family, setFamily] = useState("All"),
    [selected, setSelected] = useState("G1"),
    [failed, setFailed] = useState(false);
  const example = data.examples.find((e) => e.id === selected);
  const group = data.families.find((f) => f.id === example.family);
  const shown = data.examples.filter(
    (e) => family === "All" || e.family === family,
  );
  const ref = useRef(null);
  function choose(e) {
    setSelected(e.id);
    setFamily(e.family);
    setFailed(false);
  }
  function chooseFamily(id) {
    setFamily(id);
    if (id !== "All") {
      setSelected(data.examples.find((e) => e.family === id).id);
      setFailed(false);
    }
  }
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries[0].isIntersecting) ref.current?.pause();
      },
      { threshold: 0.1 },
    );
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, [selected]);
  return (
    <section className="explorer-section section" id="explore">
      <div className="wrap">
        <div className="section-heading">
          <div>
            <Label>EXPLORE THE BENCHMARK</Label>
            <h2 className="section-title">Five ways a world can break.</h2>
          </div>
          <p>
            Click the taxonomy to discover an anomaly.
            <br />
            Watch the evidence unfold.
          </p>
        </div>
        <div className="family-tabs" aria-label="Anomaly families">
          <button
            className={family === "All" ? "active" : ""}
            aria-pressed={family === "All"}
            onClick={() => chooseFamily("All")}
          >
            All families <span>15</span>
          </button>
          {data.families.map((f) => (
            <button
              key={f.id}
              className={family === f.id ? "active" : ""}
              onClick={() => chooseFamily(f.id)}
              aria-pressed={family === f.id}
            >
              <i style={{ background: f.color }} />
              {f.name}
            </button>
          ))}
        </div>
        <div className="explorer-layout">
          <div className="wheel-card">
            <RadialTaxonomy
              data={data}
              family={family}
              selected={selected}
              onFamily={chooseFamily}
              onExample={choose}
            />
          </div>
          <div className="demo-card" style={{ "--family-color": group.color }}>
            <div className="demo-top">
              <span className="demo-id">{selected}</span>
              <span>{group.name}</span>
            </div>
            <div className="demo-media">
              {!failed ? (
                <video
                  key={selected}
                  ref={ref}
                  controls
                  muted
                  playsInline
                  loop
                  preload="none"
                  poster={"./" + example.frames[0].src}
                  onError={() => setFailed(true)}
                  aria-label={example.title}
                >
                  <source
                    src={"./" + example.video}
                    type="video/mp4"
                    onError={() => setFailed(true)}
                  />
                </video>
              ) : (
                <img
                  src={"./" + example.frames[0].src}
                  alt={example.frames[0].caption}
                />
              )}
            </div>
            {failed && (
              <p className="error-message" role="status">
                Video unavailable. The reference image is shown instead.
              </p>
            )}
            <div className="demo-copy" aria-live="polite">
              <h3>{example.title}</h3>
              <p>{example.evidence}</p>
              <details>
                <summary>
                  What defines this anomaly? <Icon name="down" size={14} />
                </summary>
                <p>{example.definition}</p>
                {example.note && <p>{example.note}</p>}
              </details>
            </div>
          </div>
        </div>
        <div className="example-selector" aria-label="Anomaly examples">
          {shown.map((e) => (
            <button
              key={e.id}
              className={e.id === selected ? "active" : ""}
              aria-pressed={e.id === selected}
              onClick={() => choose(e)}
            >
              <img src={"./" + e.frames[0].src} alt="" loading="lazy" />
              <span>
                <b>{e.id}</b>
                {e.title}
              </span>
              {e.id === selected && <Icon name="check" size={16} />}
            </button>
          ))}
        </div>
        <p className="section-note">
          Illustrative demonstrations of the 15 anomaly types. Each
          main-evaluation task contains one target anomaly.
        </p>
      </div>
    </section>
  );
}
function Methods({ onImage }) {
  const [tab, setTab] = useState("vlm");
  return (
    <section className="section wrap methods" id="method">
      <div className="section-heading">
        <div>
          <Label>THE AUDITING LOOP</Label>
          <h2 className="section-title">Explore. Investigate. Explain.</h2>
        </div>
        <p>
          A suspicious observation is only the beginning.
          <br />
          The agent has to gather the evidence.
        </p>
      </div>
      <div className="method-steps">
        {[
          [
            "01",
            "Explore the scene",
            "Navigate a first-person 3D world and search for a potential anomaly.",
            "globe",
          ],
          [
            "02",
            "Test a hypothesis",
            "Interact, change viewpoint, or revisit a location to verify a suspicion.",
            "search",
          ],
          [
            "03",
            "Report the evidence",
            "Describe the anomaly and cite observations that support the finding.",
            "paper",
          ],
        ].map(([n, h, p, icon]) => (
          <article key={n}>
            <div className="step-top">
              <span>{n}</span>
              <Icon name={icon} size={23} />
            </div>
            <h3>{h}</h3>
            <p>{p}</p>
          </article>
        ))}
      </div>
      <div className="paradigm-panel">
        <div className="paradigm-copy">
          <div className="segmented" aria-label="Auditing paradigm">
            <button
              className={tab === "vlm" ? "active" : ""}
              aria-pressed={tab === "vlm"}
              onClick={() => setTab("vlm")}
            >
              VLM agent
            </button>
            <button
              className={tab === "vla" ? "active" : ""}
              aria-pressed={tab === "vla"}
              onClick={() => setTab("vla")}
            >
              VLA + VLM
            </button>
          </div>
          <h3>
            {tab === "vlm"
              ? "Reasoning guides every next move."
              : "Explore first. Analyze afterwards."}
          </h3>
          <p>
            {tab === "vlm"
              ? "The VLM reasons during exploration, chooses actions, retrieves earlier observations, and revises its findings. What it sees changes what it does next."
              : "A VLA collects a trajectory. A VLM then reviews the recorded observations to identify anomalies. Its analysis cannot guide the exploration that already happened."}
          </p>
          <div className="budget">
            <span>EXPLORATION BUDGET</span>
            <strong>{tab === "vlm" ? "40 actions" : "60 seconds"}</strong>
          </div>
          <p className="fine-print">
            Both paradigms submit reports and evidence to the same VLM judge.
          </p>
        </div>
        <button
          className="figure-button"
          onClick={() =>
            onImage({
              src: "./figures/auditor-modes.webp",
              alt: "Paper figure: VLM auditing and VLA–VLM auditing paradigms",
            })
          }
          aria-label="Enlarge auditing paradigms figure"
        >
          <img
            loading="lazy"
            src="./figures/auditor-modes.webp"
            alt="VLM agents reason during exploration; VLA–VLM auditors analyze a recorded trajectory."
          />
          <span>
            <Icon name="expand" size={16} /> View full figure
          </span>
        </button>
      </div>
    </section>
  );
}
function Results() {
  const [mode, setMode] = useState("vlm"),
    [metric, setMetric] = useState(5);
  const metrics = [
    "Static physics",
    "Interactive physics",
    "Spatial consistency",
    "Temporal consistency",
    "Semantic consistency",
    "Overall",
  ];
  const human = [89.8, 81.3, 76.3, 78.1, 88.6, 83.4];
  const sorted = [...scores].sort((a, b) => b[mode][metric] - a[mode][metric]);
  return (
    <section className="results-section section" id="results">
      <div className="wrap">
        <div className="section-heading">
          <div>
            <Label>THE RESULTS</Label>
            <h2 className="section-title">
              A wide gap.
              <br />
              <span>A new challenge.</span>
            </h2>
          </div>
          <p>
            Even the strongest tested agent falls short of human auditing.
            <br />
            Explore performance across models and anomaly families.
          </p>
        </div>
        <div className="results-layout">
          <div className="result-chart">
            <div className="chart-controls">
              <div
                className="segmented results-toggle"
                aria-label="Result paradigm"
              >
                <button
                  className={mode === "vlm" ? "active" : ""}
                  aria-pressed={mode === "vlm"}
                  onClick={() => setMode("vlm")}
                >
                  VLM agents
                </button>
                <button
                  className={mode === "vla" ? "active" : ""}
                  aria-pressed={mode === "vla"}
                  onClick={() => setMode("vla")}
                >
                  VLA + VLM
                </button>
              </div>
              <label className="metric-select">
                <span className="sr-only">Anomaly family</span>
                <select
                  value={metric}
                  onChange={(e) => setMetric(Number(e.target.value))}
                >
                  {[5, 0, 1, 2, 3, 4].map((i) => (
                    <option value={i} key={i}>
                      {metrics[i]}
                    </option>
                  ))}
                </select>
                <Icon name="down" size={14} />
              </label>
            </div>
            <div className="chart-axis">
              <span>SUCCESS RATE</span>
              <span>0 — 100%</span>
            </div>
            <div className="bar-chart" aria-live="polite">
              <div className="bar-row human">
                <div className="bar-name">
                  <span className="human-icon">H</span>Human
                </div>
                <div className="bar-track">
                  <div
                    className="bar-fill"
                    style={{ width: `${human[metric]}%` }}
                  />
                </div>
                <strong>
                  {human[metric].toFixed(1)}
                  <small>%</small>
                </strong>
              </div>
              <div className="chart-divider" />
              {sorted.map((m, i) => (
                <div className="bar-row" key={m.name}>
                  <div className="bar-name">
                    <img src={`./media/${m.logo}.png`} alt="" />
                    {m.name}
                  </div>
                  <div className="bar-track">
                    <div
                      className={"bar-fill " + (i === 0 ? "best" : "")}
                      style={{ width: `${m[mode][metric]}%` }}
                    />
                  </div>
                  <strong>
                    {m[mode][metric].toFixed(1)}
                    <small>%</small>
                  </strong>
                </div>
              ))}
            </div>
            <p className="chart-note">
              {metrics[metric]} ·{" "}
              {mode === "vlm"
                ? "VLM-only auditing"
                : "VLA exploration + VLM analysis"}{" "}
              · Paper Table 2
            </p>
          </div>
          <aside className="findings">
            <article>
              <span className="finding-stat">
                41.1<span>pp</span>
              </span>
              <h3>The human–agent gap</h3>
              <p>
                83.4% human success versus 42.3% for the strongest VLM agent,
                across all 213 tasks.
              </p>
            </article>
            <article>
              <span className="finding-stat">
                2.4<span>×</span>
              </span>
              <h3>Reasoning during exploration matters</h3>
              <p>
                The best VLM-only result (42.3%) is about 2.4× the best VLA–VLM
                result (17.4%).
              </p>
            </article>
            <a href={PAPER} target="_blank" rel="noreferrer">
              Read the full analysis <Icon name="arrow" />
            </a>
          </aside>
        </div>
        <details className="full-results">
          <summary>
            View complete benchmark results <Icon name="down" />
          </summary>
          <div className="table-scroll">
            <table>
              <caption>
                Success rate (%) and cost ($/task). Current paradigm:{" "}
                {mode === "vlm" ? "VLM-only" : "VLA–VLM"}.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Model</th>
                  {metrics.slice(0, 5).map((m) => (
                    <th scope="col" key={m}>
                      {m}
                    </th>
                  ))}
                  <th scope="col">Overall</th>
                  <th scope="col">Cost / task</th>
                </tr>
              </thead>
              <tbody>
                {scores.map((m) => (
                  <tr key={m.name}>
                    <th scope="row">{m.name}</th>
                    {m[mode].map((v, i) => (
                      <td key={i} className={i === 5 ? "overall" : ""}>
                        {i === 6 ? "$" + v.toFixed(3) : v.toFixed(1)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </div>
    </section>
  );
}
function Environments() {
  const [filter, setFilter] = useState("All"),
    [all, setAll] = useState(false);
  const filtered = data.environments.filter(
    (e) => filter === "All" || e.category === filter,
  );
  const shown = filter === "All" && !all ? filtered.slice(0, 6) : filtered;
  return (
    <section className="section wrap" id="environments">
      <div className="section-heading">
        <div>
          <Label>THE WORLDS</Label>
          <h2 className="section-title">
            13 environments.
            <br />
            <span>Endless places to look.</span>
          </h2>
        </div>
        <p>
          From furnished interiors to ancient cities and open landscapes.
          <br />
          <b>126 Unreal Engine tasks · 87 Three.js tasks.</b>
        </p>
      </div>
      <div className="environment-filters" aria-label="Environment categories">
        {["All", "Indoor", "City", "History", "Industrial", "Nature"].map(
          (c) => (
            <button
              key={c}
              className={filter === c ? "active" : ""}
              aria-pressed={filter === c}
              onClick={() => setFilter(c)}
            >
              {c}
              {c === "All" && <span>13</span>}
            </button>
          ),
        )}
      </div>
      <div className="environment-grid">
        {shown.map((e) => (
          <article key={e.slug} className="environment-card">
            <div className="environment-image">
              <img src={"./" + e.image} alt={e.name} loading="lazy" />
              <span>{e.engine}</span>
              <div className="environment-overlay" />
            </div>
            <div className="environment-copy">
              <span className="environment-category">
                {e.category}
                <span>{e.tasks} tasks</span>
              </span>
              <h3>{e.name}</h3>
              <details>
                <summary>
                  Explore the setting <Icon name="down" size={14} />
                </summary>
                <p>{e.scene_description}</p>
              </details>
            </div>
          </article>
        ))}
      </div>
      {filter === "All" && (
        <button
          className="button secondary show-all"
          onClick={() => setAll(!all)}
        >
          {all ? "Show fewer environments" : "Discover all 13 environments"}
          <Icon name={all ? "down" : "arrow"} />
        </button>
      )}
    </section>
  );
}
function Citation() {
  const [copied, setCopied] = useState(false),
    [error, setError] = useState(false);
  const timer = useRef();
  useEffect(() => () => clearTimeout(timer.current), []);
  async function copy() {
    try {
      await navigator.clipboard.writeText(bib);
      setCopied(true);
      setError(false);
      timer.current = setTimeout(() => setCopied(false), 2500);
    } catch {
      setError(true);
    }
  }
  return (
    <section className="section wrap citation" id="citation">
      <h2 className="section-title">Citation</h2>
      <div className="bib-card">
        <div className="bib-toolbar">
          <span>BibTeX</span>
          <button onClick={copy} aria-label="Copy citation">
            <Icon name={copied ? "check" : "copy"} size={15} />
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>
        <pre>
          <code>{bib}</code>
        </pre>
        {error && (
          <p role="status">
            Select the citation above and copy it with your keyboard.
          </p>
        )}
      </div>
    </section>
  );
}
function Lightbox({ image, onClose }) {
  const ref = useRef(null);
  useEffect(() => {
    if (image) {
      ref.current.showModal();
      document.body.style.overflow = "hidden";
    } else {
      ref.current?.close();
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [image]);
  return (
    <dialog
      className="lightbox"
      ref={ref}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      aria-label={image?.alt || "Enlarged figure"}
    >
      <button
        className="icon-button lightbox-close"
        onClick={onClose}
        aria-label="Close enlarged figure"
      >
        <Icon name="close" />
      </button>
      {image && <img src={image.src} alt={image.alt} />}
    </dialog>
  );
}
function App() {
  const [image, setImage] = useState(null);
  return (
    <>
      <a className="skip-link" href="#overview">
        Skip to content
      </a>
      <Header />
      <main>
        <Hero />
        <Overview />
        <Explorer />
        <Methods onImage={setImage} />
        <Results />
        <Environments />
        <Citation />
      </main>
      <footer>
        <div className="wrap footer-inner">
          <a href="#top" className="brand">
            <Mark />
            <span>WorldAuditBench</span>
          </a>
          <p>UC Santa Barbara · MIT CSAIL · MIT-IBM Watson AI Lab</p>
          <a href="#top">Back to top ↑</a>
        </div>
      </footer>
      <Lightbox image={image} onClose={() => setImage(null)} />
    </>
  );
}
createRoot(document.getElementById("root")).render(<App />);
