import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

const mediaUrl = (path) =>
  window.__worldauditAssets?.[path] ||
  (/^(https?:|data:|blob:)/.test(path) ? path : `./${path}`);
function Mark() {
  return (
    <img
      className="project-logo"
      src={mediaUrl("media/worldaudit-logo.png")}
      alt="WorldAuditBench logo"
    />
  );
}
function point(radius, angle) {
  const a = ((angle - 90) * Math.PI) / 180;
  return [340 + radius * Math.cos(a), 340 + radius * Math.sin(a)];
}
function sector(inner, outer, start, end) {
  const a = point(outer, start),
    b = point(outer, end),
    c = point(inner, end),
    d = point(inner, start);
  return `M${a} A${outer},${outer} 0 ${end - start > 180 ? 1 : 0} 1 ${b} L${c} A${inner},${inner} 0 ${end - start > 180 ? 1 : 0} 0 ${d} Z`;
}
function useAnimatedFamilyWidths(families, family) {
  const [widths, setWidths] = useState(() => families.map(() => 72));
  const current = useRef(widths);
  useEffect(() => {
    const target = families.map((f) =>
      family === "All" ? 72 : f.id === family ? 104 : 64,
    );
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      current.current = target;
      setWidths(target);
      return;
    }
    const from = [...current.current];
    let handle;
    let start;
    const tick = (time) => {
      if (start === undefined) start = time;
      const t = Math.min((time - start) / 480, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      const next = from.map((value, i) => value + (target[i] - value) * eased);
      current.current = next;
      setWidths(next);
      if (t < 1) handle = requestAnimationFrame(tick);
    };
    handle = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(handle);
  }, [family, families]);
  return widths;
}
export function RadialTaxonomy({
  data,
  family,
  selected,
  onFamily,
  onExample,
}) {
  const widths = useAnimatedFamilyWidths(data.families, family);
  const [hover, setHover] = useState(null);
  const active = hover || selected;
  const activeExample = data.examples.find((e) => e.id === active);
  const activeFamily = data.families.find(
    (f) => f.id === (activeExample?.family || active),
  );
  const keyboard = (callback) => (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      callback();
    }
  };
  return (
    <div className="taxonomy-panel">
      <div className="taxonomy-drawing">
        <svg
          className="taxonomy-chart"
          viewBox="0 0 680 680"
          aria-label="Interactive anomaly taxonomy. Select a family or subtype."
          role="group"
        >
          <circle
            cx="340"
            cy="340"
            r="318"
            fill="none"
            stroke="#304153"
            strokeDasharray="2 8"
          />
          {data.families.map((f, fi) => {
            const start =
                widths.slice(0, fi).reduce((sum, w) => sum + w, 0) - 36,
              end = start + widths[fi];
            const children = data.examples.filter((e) => e.family === f.id);
            const pos = point(133, (start + end) / 2);
            const words = f.name.split(" ");
            return (
              <g key={f.id} style={{ "--sector": f.color }}>
                <g
                  role="button"
                  tabIndex="0"
                  aria-label={`Show ${f.name} examples`}
                  aria-pressed={family === f.id}
                  className={`family-sector ${family === f.id ? "is-active" : ""}`}
                  onClick={() => onFamily(f.id)}
                  onKeyDown={keyboard(() => onFamily(f.id))}
                  onMouseEnter={() => setHover(f.id)}
                  onMouseLeave={() => setHover(null)}
                  onFocus={() => setHover(f.id)}
                  onBlur={() => setHover(null)}
                >
                  <path d={sector(70, 194, start + 1, end - 1)} />
                  <text x={pos[0]} y={pos[1] - 8} textAnchor="middle">
                    {words.map((word, i) => (
                      <tspan x={pos[0]} dy={i ? 19 : 0} key={word}>
                        {word}
                      </tspan>
                    ))}
                  </text>
                  <title>{`${f.name}: ${f.description}`}</title>
                </g>
                {children.map((e, ei) => {
                  const a = start + (ei * widths[fi]) / children.length,
                    b = start + ((ei + 1) * widths[fi]) / children.length,
                    mid = (a + b) / 2,
                    p = point(249, mid);
                  let rotation = mid;
                  if (mid > 90 && mid < 270) rotation += 180;
                  return (
                    <g
                      key={e.id}
                      style={{
                        transform:
                          selected === e.id
                            ? `translate(${Math.sin((mid * Math.PI) / 180) * 5}px,${-Math.cos((mid * Math.PI) / 180) * 5}px)`
                            : "translate(0px,0px)",
                      }}
                      role="button"
                      tabIndex="0"
                      aria-label={`Show ${e.id}: ${e.subtype}`}
                      aria-pressed={selected === e.id}
                      className={`subtype-sector ${selected === e.id ? "is-active" : ""} ${family !== "All" && family !== f.id ? "is-muted" : ""}`}
                      onClick={() => onExample(e)}
                      onKeyDown={keyboard(() => onExample(e))}
                      onMouseEnter={() => setHover(e.id)}
                      onMouseLeave={() => setHover(null)}
                      onFocus={() => setHover(e.id)}
                      onBlur={() => setHover(null)}
                    >
                      <path d={sector(201, 308, a + 0.7, b - 0.7)} />
                      <text
                        textAnchor="middle"
                        transform={`translate(${p}) rotate(${rotation})`}
                      >
                        <tspan className="sector-code" x="0" y="-17">
                          {e.id}
                        </tspan>
                        {e.chartLabel.map((line, i) => (
                          <tspan key={line} x="0" dy="16">
                            {line}
                          </tspan>
                        ))}
                      </text>
                      <title>{e.subtype}</title>
                    </g>
                  );
                })}
              </g>
            );
          })}
          <g
            role="button"
            tabIndex="0"
            aria-label="Show all examples"
            className="taxonomy-center"
            onClick={() => onFamily("All")}
            onKeyDown={keyboard(() => onFamily("All"))}
          >
            <circle cx="340" cy="340" r="62" fill="#fff" />
            <image
              href={mediaUrl("media/worldaudit-logo.png")}
              xlinkHref={mediaUrl("media/worldaudit-logo.png")}
              x="309"
              y="305"
              width="62"
              height="62"
            />
            <text x="340" y="385" textAnchor="middle">
              ALL EXAMPLES
            </text>
          </g>
        </svg>
        <p className="taxonomy-hint">
          Select a family or subtype to inspect its examples.
        </p>
      </div>
      <div className="taxonomy-details">
        <p className="eyebrow">
          {activeFamily?.name || "Explore the taxonomy"}
        </p>
        <p className="taxonomy-description">
          {activeExample?.subtype || activeFamily?.description}
        </p>
        <button className="taxonomy-reset" onClick={() => onFamily("All")}>
          Show all examples
        </button>
      </div>
    </div>
  );
}
