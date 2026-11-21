/* Ducky Auto's page on Settings → LLMs → Ducky Auto, drawn straight into the provider's
 * ducky:llm-slot mount (no iframe). Model fields are the chat's own picker (host.mountModelPicker),
 * the gateway choice the app's dropdown (host.mountChoiceDropdown); data comes from the backend's
 * panel RPCs through host.call. */
(() => {
  const PID = "ducky-auto";
  const PROVIDER = "ducky_auto";
  // An older copy of this page (same app session) steps aside first.
  try { window.__duckyPluginBootCleanups?.[PID]?.(); } catch { /* gone */ }

  const TASK_NAMES = {
    planning: "Planning", coding: "Coding", modeling: "Modeling", research: "Research",
    writing: "Writing", quick: "Quick questions", execution: "Tool steps", general: "Everything else",
  };
  const WHEN = { execution: "When the step only runs tools", general: "When no rule above matched" };
  const GATEWAYS = [
    ["", "Any with a key"], ["anthropic", "Anthropic"], ["openai", "OpenAI"], ["gemini", "Gemini"],
    ["spacexai", "SpaceX AI"], ["kimi", "Kimi"], ["ollama", "Ollama"],
  ];
  const TABS = [["rules", "Rules"], ["analytics", "Analytics"], ["changes", "Changes"], ["sharing", "Sharing"]];
  const DECISIONS = {
    first: ["First step", "amber"], same: ["Same model", "muted"], switched: ["Switched", "accent"],
    kept: ["Kept (cheaper)", "green"], "stayed (tool step)": ["Stayed (tool step)", "blue"],
    "kept (nothing else answered)": ["Kept (nothing else answered)", "red"],
  };
  const OUTCOMES = [["Same model", "muted"], ["Switched", "accent"], ["Kept (cheaper)", "green"], ["Stayed (tool step)", "blue"]];
  const PALETTE = ["accent", "blue", "green", "amber", "red", "muted", "fg"];
  const KINDS = { pick_cant_run: ["Can't run", "red"], high_error: ["Errors", "red"], slow: ["Slow", "amber"], slow_checks: ["Slow checks", "muted"] };
  const BY = { you: "accent", agent: "amber", setup: "green", tune: "muted" };
  const TOOLS = [
    ["check", "Check my models", "Checking…", "Tries each rule's model live."],
    ["setup", "Set up for me", "Setting up…", "Pins a working model per rule. Keeps picks that work."],
    ["tune", "Suggest changes", "Looking…", "Finds errors and slow models in recent steps."],
  ];
  const JOBTXT = {
    check: ["Checking every rule's model", "Up to 3 minutes. Keep editing; results land here and on each rule."],
    setup: ["Setting up", "Checking models and picking one per rule. Up to 3 minutes."],
    tune: ["Looking at your last 500 steps", "Suggestions appear here."],
  };
  const NUMBERS = [
    ["short_question_chars", "Short question (characters)", "A message ending in “?” that is shorter than this counts as Quick."],
    ["small_context", "Small context (tokens)", "When prices aren't known, a chat only switches model while it is under this size."],
    ["steps_ahead", "Steps ahead", "How many steps a model switch must pay itself back over."],
  ];
  const RAISED = "color-mix(in srgb,var(--fg) 5%,var(--card))";
  const HOVER = "color-mix(in srgb,var(--fg) 7%,transparent)";
  const MONO = "'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace";

  const CSS = `
.dka{display:flex;flex-direction:column;gap:20px;color:var(--fg);font-size:14px;max-width:1240px}
.dka button,.dka input{font-family:inherit}
.dka button:focus-visible,.dka input:focus-visible,.dka [tabindex]:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.dka-mono{font-family:${MONO}}
.dka-muted{color:var(--muted)}
.dka-c-accent{color:var(--accent)}.dka-c-blue{color:var(--blue)}.dka-c-green{color:var(--green)}.dka-c-amber{color:var(--amber)}.dka-c-red{color:var(--red)}.dka-c-muted{color:var(--muted)}.dka-c-fg{color:var(--fg)}
.dka-b-accent{background:var(--accent)}.dka-b-blue{background:var(--blue)}.dka-b-green{background:var(--green)}.dka-b-amber{background:var(--amber)}.dka-b-red{background:var(--red)}.dka-b-muted{background:var(--muted)}.dka-b-fg{background:var(--fg)}
.dka-t-accent{background:color-mix(in srgb,var(--accent) 15%,transparent);color:var(--accent)}
.dka-t-blue{background:color-mix(in srgb,var(--blue) 15%,transparent);color:var(--blue)}
.dka-t-green{background:color-mix(in srgb,var(--green) 15%,transparent);color:var(--green)}
.dka-t-amber{background:color-mix(in srgb,var(--amber) 15%,transparent);color:var(--amber)}
.dka-t-red{background:color-mix(in srgb,var(--red) 15%,transparent);color:var(--red)}
.dka-t-muted{background:color-mix(in srgb,var(--muted) 15%,transparent);color:var(--muted)}
.dka-head{display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap}
.dka-head-text{flex:1 1 320px;display:flex;flex-direction:column;gap:4px}
.dka-crumb{font-size:12px;color:var(--muted)}
.dka-title{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.dka-title h1{margin:0;font-size:24px;font-weight:700;letter-spacing:-.01em}
.dka-title span{font-size:12px;color:var(--muted);font-family:${MONO}}
.dka-lede{font-size:14px;color:var(--muted)}
.dka-tabs{display:flex;gap:2px;padding:3px;border-radius:999px;border:1px solid var(--border);background:var(--card);overflow-x:auto;scrollbar-width:none}
.dka-tab{height:34px;padding:0 14px;border-radius:999px;border:none;background:transparent;color:var(--muted);font-size:13px;font-weight:600;cursor:pointer;display:inline-flex;align-items:center;gap:7px;white-space:nowrap;transition:all .15s}
.dka-tab:hover{color:var(--fg)}
.dka-tab.is-on{background:${RAISED};color:var(--fg)}
.dka-badge{min-width:18px;height:18px;padding:0 5px;border-radius:999px;background:var(--amber);color:var(--card);font-size:11px;font-weight:700;display:inline-grid;place-items:center}
.dka-card{background:var(--card);border:1px solid var(--border);border-radius:14px}
.dka-note-card{padding:20px;border-radius:12px;border:1px solid var(--border);background:var(--card)}
.dka-loading{padding:24px 0;color:var(--muted);display:flex;gap:10px;align-items:center}
.dka-spin{width:14px;height:14px;border-radius:50%;border:2px solid var(--border);border-top-color:var(--accent);animation:dka-spin .8s linear infinite;flex:none;display:inline-block}
.dka-spin.is-on-accent{width:12px;height:12px;border-color:color-mix(in srgb,var(--card) 35%,transparent);border-top-color:var(--card)}
@keyframes dka-spin{to{transform:rotate(360deg)}}
@keyframes dka-indet{0%{left:-35%}100%{left:100%}}
@keyframes dka-flash{0%{box-shadow:0 0 0 3px color-mix(in srgb,var(--green) 45%,transparent)}100%{box-shadow:0 0 0 0 transparent}}
.dka-err{padding:16px;border-radius:12px;border:1px solid color-mix(in srgb,var(--red) 40%,transparent);background:color-mix(in srgb,var(--red) 8%,var(--card));display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.dka-err span{flex:1;color:var(--red);font-weight:500}
.dka-btn{height:34px;padding:0 14px;border-radius:8px;border:1px solid var(--border);background:var(--card);color:var(--fg);font-size:13px;cursor:pointer;display:inline-flex;align-items:center;gap:8px;white-space:nowrap;transition:all .15s}
.dka-btn:hover:not(:disabled){border-color:var(--accent)}
.dka-btn.is-ghost{border-color:transparent;background:transparent;color:var(--muted)}
.dka-btn.is-ghost:hover{color:var(--fg);background:${HOVER};border-color:transparent}
.dka-btn.is-primary{border:none;background:var(--accent);color:var(--card);font-weight:700}
.dka-btn.is-raised{background:${RAISED};font-weight:600;height:36px}
.dka-btn.is-armed,.dka-icon.is-armed{background:color-mix(in srgb,var(--red) 14%,transparent);border-color:var(--red);color:var(--red);font-weight:600}
.dka-col{display:flex;flex-direction:column;gap:16px}
.dka-try{padding:16px;display:flex;flex-direction:column;gap:12px}
.dka-try-row{display:flex;gap:8px;flex-wrap:wrap}
.dka-input{height:38px;padding:0 12px;border-radius:8px;border:1px solid var(--border);background:var(--bg);color:var(--fg);font-size:14px;outline:none}
.dka-input:focus{border-color:var(--accent)}
.dka-try-row .dka-input{flex:1 1 320px;height:48px;padding:0 16px;border-radius:10px;font-size:15px}
.dka-try-row .dka-btn{height:48px;padding:0 22px;border-radius:10px;font-size:15px}
.dka-try-row .dka-btn:disabled{opacity:.6;cursor:default}
.dka-small{font-size:13px;color:var(--muted)}
.dka-trace{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:14px}
.dka-task-pill{display:inline-flex;align-items:center;height:30px;padding:0 12px;border-radius:999px;background:color-mix(in srgb,var(--accent) 14%,transparent);color:var(--accent);font-weight:700}
.dka-split{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start}
.dka-flow{flex:1 1 600px;min-width:0;padding:18px;display:flex;flex-direction:column;gap:16px}
.dka-side{flex:0 1 340px;min-width:280px;display:flex;flex-direction:column;gap:16px;position:sticky;top:16px}
.dka-step-head{display:flex;align-items:flex-start;gap:12px;flex-wrap:wrap}
.dka-step-head>div{flex:1 1 280px}
.dka-kicker{font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.dka-step-title{font-size:17px;font-weight:700;margin-top:2px}
.dka-step-sub{font-size:13px;color:var(--muted);margin-top:2px;line-height:1.5}
.dka-step{border-top:1px solid var(--border);padding-top:16px;display:flex;flex-direction:column;gap:12px}
.dka-add{border:1px dashed var(--accent);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:10px}
.dka-add-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.dka-add-row .dka-name{flex:1 1 200px}
.dka-add-row .dka-kw{flex:2 1 240px;font-family:${MONO}}
.dka-hint{flex:1;font-size:12px;color:var(--muted)}
.dka-hint.is-bad{color:var(--red)}
.dka-tl{display:flex;flex-direction:column}
.dka-tl-start{display:grid;grid-template-columns:36px minmax(0,1fr);align-items:center}
.dka-tl-start>div:first-child{display:flex;justify-content:center}
.dka-start-dot{width:14px;height:14px;border-radius:50%;background:var(--muted);box-shadow:0 0 0 4px color-mix(in srgb,var(--muted) 22%,transparent)}
.dka-start-dot.is-on{background:var(--accent);box-shadow:0 0 0 4px color-mix(in srgb,var(--accent) 22%,transparent)}
.dka-start-label{padding-left:8px;font-size:13px;font-weight:600;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dka-start-label.is-on{color:var(--fg)}
.dka-sep{display:grid;grid-template-columns:36px minmax(0,1fr);min-height:44px}
.dka-sep>div:first-child{display:flex;justify-content:center}
.dka-sep>div:last-child{display:flex;align-items:center;gap:10px;padding-left:8px}
.dka-sep>div:last-child span:last-child{flex:1;height:1px;background:var(--border)}
.dka-line{width:2px;background:var(--border);transition:background .25s}
.dka-line.is-lit{background:var(--accent)}
.dka-tl-row{display:grid;grid-template-columns:36px minmax(0,1fr);transition:opacity .25s}
.dka-tl-row.is-skipped{opacity:.55}
.dka-tl-row.is-unreached{opacity:.35}
.dka-rail{display:flex;flex-direction:column;align-items:center}
.dka-rail .dka-line:first-child{height:18px}
.dka-rail .dka-line:last-child{flex:1}
.dka-node{width:28px;height:28px;border-radius:50%;border:2px solid var(--border);background:var(--card);color:var(--muted);display:grid;place-items:center;font-size:12px;font-weight:700;flex:none;font-variant-numeric:tabular-nums;transition:all .25s}
.is-skipped .dka-node{border-color:var(--accent);color:var(--accent)}
.is-matched .dka-node{border-color:var(--accent);background:var(--accent);color:var(--card)}
.dka-tl-body{padding:8px 0 4px 8px;min-width:0}
.dka-task{border:1px solid var(--border);border-radius:12px;background:var(--card);padding:12px 14px;display:flex;flex-direction:column;gap:10px;transition:border-color .2s,box-shadow .2s,background .2s}
.dka-task.is-bad{border-color:color-mix(in srgb,var(--red) 45%,transparent)}
.is-matched .dka-task{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 6%,var(--card));box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 18%,transparent)}
.dka-task.is-flash{animation:dka-flash 2s ease-out}
.dka-task-head{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.dka-task-name{font-size:15px;font-weight:700}
.dka-yours{padding:1px 7px;border-radius:999px;border:1px solid var(--border);font-size:11px;color:var(--muted)}
.dka-tag{padding:2px 8px;border-radius:999px;background:${RAISED};color:var(--muted);font-size:11px;font-weight:700}
.is-matched .dka-tag{background:var(--accent);color:var(--card)}
.dka-check{display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700}
.dka-dot{width:6px;height:6px;border-radius:50%;flex:none;display:inline-block}
.dka-dot.is-8{width:8px;height:8px}
.dka-grow{flex:1}
.dka-moves{display:flex;gap:2px}
.dka-icon{width:28px;height:28px;border-radius:6px;border:1px solid var(--border);background:transparent;color:var(--fg);cursor:pointer;transition:all .15s}
.dka-icon:hover:not(:disabled){background:${HOVER}}
.dka-icon:disabled{opacity:.3;cursor:default}
.dka-del{width:auto;min-width:28px;padding:0 8px;color:var(--muted);font-size:12px;font-weight:600;white-space:nowrap}
.dka-task-body{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.dka-chips{flex:1 1 280px;min-width:0;display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:5px 6px;min-height:40px;border:1px solid var(--border);border-radius:8px;background:var(--bg);cursor:text}
.dka-chips:focus-within{border-color:var(--accent)}
.dka-chip{display:inline-flex;align-items:center;gap:2px;height:28px;padding:0 4px 0 10px;border-radius:6px;background:${RAISED};border:1px solid var(--border);color:var(--fg);font-family:${MONO};font-size:12px}
.dka-chip.is-hit{background:color-mix(in srgb,var(--accent) 18%,transparent);border-color:var(--accent);color:var(--accent);font-weight:700}
.dka-chip button{width:22px;height:22px;border:none;border-radius:4px;background:transparent;color:var(--muted);cursor:pointer;font-size:13px}
.dka-chip button:hover{color:var(--red)}
.dka-chip-in{flex:1;min-width:110px;height:28px;border:none;background:transparent;color:var(--fg);font-size:13px;font-family:${MONO};outline:none}
.dka-when{flex:1 1 280px;min-width:0;min-height:40px;display:flex;align-items:center;padding:0 12px;border-radius:8px;background:${RAISED};font-size:13px;color:var(--muted)}
.dka-arrow{flex:none;font-size:18px;color:var(--border);transition:color .25s}
.is-matched .dka-arrow{color:var(--accent)}
.dka-picker{flex:0 1 280px;min-width:220px;min-height:40px;display:flex;align-items:center}
.dka-picker>*{flex:1}
.dka-warn{font-size:13px;color:var(--amber)}
.dka-fail{font-size:13px;color:var(--red)}
.dka-chain{display:flex;gap:8px;flex-wrap:wrap;align-items:stretch}
.dka-chain-item{flex:1 1 200px;display:flex;align-items:stretch;gap:8px;min-width:0}
.dka-chain-card{flex:1;border:1px solid var(--border);background:${RAISED};border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:4px;transition:all .25s}
.dka-chain-card.is-used{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 8%,var(--card))}
.dka-chain-card.is-before{opacity:.65}
.dka-chain-card.is-after{opacity:.4}
.dka-chain-head{display:flex;gap:8px;align-items:center}
.dka-num{width:20px;height:20px;border-radius:50%;background:var(--border);color:var(--fg);display:grid;place-items:center;font-size:11px;font-weight:700;flex:none}
.is-used .dka-num{background:var(--accent);color:var(--card)}
.dka-chain-title{font-size:14px;font-weight:700;flex:1}
.dka-chain-state{font-size:11px;font-weight:700;color:var(--muted);white-space:nowrap}
.is-used .dka-chain-state{color:var(--accent)}
.dka-chain-state.is-bad{color:var(--red)}
.dka-chain-desc{font-size:12px;color:var(--muted);line-height:1.45}
.dka-chain-arrow{align-self:center;color:var(--muted);font-size:16px}
.dka-step3{border-top:1px solid var(--border);padding-top:16px;display:flex;gap:12px;align-items:flex-start;flex-wrap:wrap}
.dka-step3>div:first-child{flex:1 1 260px}
.dka-outcomes{display:flex;gap:6px;flex-wrap:wrap}
.dka-outcome{display:inline-flex;align-items:center;gap:6px;height:30px;padding:0 12px;border-radius:999px;background:${RAISED};font-size:12px;font-weight:600}
.dka-health{padding:16px;display:flex;flex-direction:column;gap:12px}
.dka-health-head{display:flex;align-items:center;gap:8px}
.dka-health-head b{font-size:15px;font-weight:700;flex:1}
.dka-status{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600}
.dka-tool{width:100%;text-align:left;padding:10px 12px;border-radius:10px;border:1px solid var(--border);background:${RAISED};color:var(--fg);cursor:pointer;display:flex;align-items:center;gap:10px;transition:border-color .15s}
.dka-tool:hover:not(:disabled){border-color:var(--accent)}
.dka-tool:disabled{cursor:progress}
.dka-tool>div{flex:1;min-width:0}
.dka-tool-label{font-size:14px;font-weight:600}
.dka-tool-tip{font-size:12px;color:var(--muted);margin-top:1px;line-height:1.4}
.dka-job{position:relative;overflow:hidden;padding:10px 12px;border-radius:10px;border:1px solid var(--border);display:flex;flex-direction:column;gap:2px}
.dka-job-title{font-size:13px;font-weight:600}
.dka-job-title span{font-weight:400;color:var(--muted);font-variant-numeric:tabular-nums}
.dka-job-sub{font-size:12px;color:var(--muted);line-height:1.4}
.dka-job-bar{position:absolute;left:0;right:0;bottom:0;height:2px;overflow:hidden}
.dka-job-bar::after{content:"";position:absolute;top:0;width:35%;height:100%;background:var(--accent);animation:dka-indet 1.4s ease-in-out infinite}
.dka-result{border-radius:10px;border:1px solid var(--border);padding:12px;display:flex;flex-direction:column;gap:8px}
.dka-result.is-bad{border-color:color-mix(in srgb,var(--red) 45%,transparent)}
.dka-result-head{display:flex;align-items:flex-start;gap:8px}
.dka-result-head .dka-dot{margin-top:6px}
.dka-result-title{flex:1;font-size:14px;font-weight:700;line-height:1.4}
.dka-x{width:24px;height:24px;border-radius:6px;border:none;background:transparent;color:var(--muted);font-size:15px;cursor:pointer}
.dka-x:hover{background:${HOVER};color:var(--fg)}
.dka-result-sub{font-size:12px;color:var(--muted);line-height:1.45}
.dka-rline{display:flex;flex-direction:column;gap:1px;padding-top:8px;border-top:1px solid var(--border);font-size:12px}
.dka-rline>div{display:flex;gap:6px}
.dka-rline>div span:first-child{font-weight:600;flex:1}
.dka-rline>div span:last-child{font-weight:700}
.dka-rline>span{font-family:${MONO};overflow-wrap:anywhere}
.dka-sugg{display:flex;flex-direction:column;gap:6px;padding-top:10px;border-top:1px solid var(--border)}
.dka-sugg-head{display:flex;gap:8px;align-items:center}
.dka-kind{padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700;white-space:nowrap}
.dka-sugg-task{font-size:13px;font-weight:600}
.dka-sugg-why{font-size:12px;color:var(--muted);line-height:1.5}
.dka-apply{align-self:flex-start;height:30px;padding:0 12px;border-radius:8px;border:none;background:var(--accent);color:var(--card);font-size:12px;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.dka-apply:disabled{opacity:.6;cursor:progress}
.dka-applied{font-size:12px;font-weight:600;color:var(--green)}
.dka-gw{display:flex;flex-direction:column;gap:6px;padding-top:12px;border-top:1px solid var(--border)}
.dka-gw>span{font-size:12px;color:var(--muted)}
.dka-numbers-btn{width:100%;padding:14px 16px;border:none;background:transparent;color:var(--fg);cursor:pointer;display:flex;align-items:flex-start;gap:10px;text-align:left}
.dka-numbers-btn>span:first-child{width:12px;color:var(--muted);padding-top:1px}
.dka-numbers-btn b{display:block;font-size:14px;font-weight:700}
.dka-numbers-btn small{display:block;font-size:12px;color:var(--muted);margin-top:2px}
.dka-numbers{padding:0 16px 16px;display:flex;flex-direction:column;gap:12px}
.dka-number{display:flex;flex-direction:column;gap:6px;padding-top:12px;border-top:1px solid var(--border)}
.dka-number>div{display:flex;gap:10px;align-items:center}
.dka-number>div span{flex:1;font-size:13px;font-weight:600}
.dka-number input{width:96px;height:34px;text-align:right;font-size:13px;font-variant-numeric:tabular-nums}
.dka-number>span,.dka-reset>span{font-size:12px;color:var(--muted);line-height:1.45}
.dka-reset{display:flex;flex-direction:column;gap:8px;padding-top:12px;border-top:1px solid var(--border)}
.dka-reset .dka-btn{align-self:flex-start;font-weight:600}
.dka-bar-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.dka-bar-row b{flex:1;font-size:15px;font-weight:700}
.dka-tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px}
.dka-tile{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:4px}
.dka-tile b{font-size:24px;font-weight:700;letter-spacing:-.01em;font-variant-numeric:tabular-nums}
.dka-tile span{font-size:13px;color:var(--muted)}
.dka-sk{padding:18px;display:flex;flex-direction:column;gap:14px}
.dka-sk-head{display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap}
.dka-sk-head>div{flex:1 1 280px}
.dka-sk-head b{font-size:15px;font-weight:700}
.dka-sk-cap{font-size:13px;color:var(--muted);min-height:18px}
.dka-sk-cap.is-on{color:var(--fg);font-weight:600}
.dka-sk-scroll{overflow-x:auto;overflow-y:hidden;padding:12px 0 16px}
.dka-sk-inner{min-width:680px;display:flex;flex-direction:column;gap:8px}
.dka-sk-cols{display:grid;grid-template-columns:1fr 1fr 1fr;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.dka-sk-cols span:nth-child(2){text-align:center}.dka-sk-cols span:nth-child(3){text-align:right}
.dka-sk-area{position:relative}
.dka-sk-area svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.dka-band{cursor:pointer;transition:fill-opacity .15s}
.dka-sk-node{position:absolute;width:10px;border-radius:3px;cursor:pointer;transition:opacity .15s}
.dka-sk-label{position:absolute;transform:translateY(-50%);display:flex;cursor:pointer;transition:opacity .15s}
.dka-sk-label span{padding:1px 6px;border-radius:4px;background:var(--card);font-size:12px;white-space:nowrap}
.dka-sk-label b{font-weight:600}
.dka-table{overflow:hidden}
.dka-table-head{padding:14px 16px 8px}
.dka-table-head b{font-size:15px;font-weight:700}
.dka-table-head div{font-size:12px;color:var(--muted);margin-top:2px}
.dka-table-scroll{overflow-x:auto}
.dka-table-inner{padding:0 16px 8px}
.dka-grid{display:grid;gap:12px;padding:9px 0;border-bottom:1px solid var(--border);font-size:13px;align-items:center}
.dka-grid.is-head{padding:8px 0;font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.dka-grid>span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-variant-numeric:tabular-nums}
.dka-r{text-align:right}
.dka-strong{font-weight:600}
.dka-empty{padding:16px 0;color:var(--muted);font-size:13px}
.dka-changes{overflow:hidden}
.dka-change{display:grid;grid-template-columns:84px 64px minmax(0,1fr);gap:14px;padding:12px 16px;border-bottom:1px solid var(--border);align-items:start}
.dka-change:last-child{border-bottom:none}
.dka-change>span:first-child{font-size:12px;color:var(--muted);padding-top:2px;font-variant-numeric:tabular-nums}
.dka-change .dka-kind{justify-self:start}
.dka-change-what{display:flex;flex-direction:column;gap:3px;min-width:0}
.dka-change-what>div{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;font-size:13px}
.dka-change-what>div span:first-child{font-weight:600}
.dka-before{font-family:${MONO};color:var(--muted);overflow-wrap:anywhere}
.dka-after{font-family:${MONO};font-weight:700;overflow-wrap:anywhere}
.dka-change-what>span{font-size:12px;color:var(--muted);line-height:1.45}
.dka-share{padding:16px;display:flex;align-items:center;gap:16px}
.dka-share>div{flex:1}
.dka-share b{font-size:15px;font-weight:700}
.dka-switch{width:46px;height:28px;border-radius:999px;border:none;padding:3px;background:var(--border);cursor:pointer;flex:none;transition:background .2s}
.dka-switch span{display:block;width:22px;height:22px;border-radius:50%;background:var(--fg);transition:transform .2s}
.dka-switch[aria-checked="true"]{background:var(--accent)}
.dka-switch[aria-checked="true"] span{transform:translateX(18px);background:var(--card)}
.dka-explain{font-size:14px;line-height:1.6;color:var(--muted);max-width:680px}
.dka-explain b{color:var(--fg);font-weight:600}
.dka-share-status{display:flex;gap:16px;flex-wrap:wrap;align-items:center;padding:12px 16px;border-radius:10px;background:var(--card);border:1px solid var(--border);font-size:13px;color:var(--muted)}
.dka-share-status b{color:var(--fg);font-weight:600}
.dka-props .dka-grid{grid-template-columns:180px minmax(0,1fr);padding:7px 0;font-family:${MONO}}
.dka-props .dka-grid.is-head{font-family:inherit;padding:8px 0}
.dka-props .dka-grid>span{white-space:normal;overflow-wrap:anywhere}
`;

  let state = null;

  const host = () => window.__duckyPluginHost?.forPlugin?.(PID) || null;
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const num = (v) => (typeof v === "number" ? v.toLocaleString() : "–");
  const fmtK = (n) => (typeof n !== "number" ? "–" : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1000 ? `${(n / 1000).toFixed(n >= 1e4 ? 0 : 1)}k` : String(Math.round(n)));
  const usd = (v) => (typeof v === "number" ? `$${v.toFixed(v < 1 ? 4 : 2)}` : "–");
  const pct = (v) => (typeof v === "number" ? `${(v * 100).toFixed(1)}%` : "–");
  const secs = (ms) => (ms ? `${(ms / 1000).toFixed(1)} s` : "–");
  const ago = (t) => {
    const m = Math.max(0, (Date.now() / 1000 - (t || 0)) / 60);
    return m < 1 ? "just now" : m < 60 ? `${Math.floor(m)}m ago` : m < 1440 ? `${Math.floor(m / 60)}h ago` : `${Math.floor(m / 1440)}d ago`;
  };
  const clock = (since) => {
    const s = Math.max(0, Math.floor((Date.now() - since) / 1000));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  };
  const taskName = (t) => TASK_NAMES[t] || state?.rules?.rules?.custom?.[t]?.label || t;
  const spin = (cls = "") => `<span class="dka-spin ${cls}" aria-hidden="true"></span>`;
  const dot = (c, big) => `<span class="dka-dot dka-b-${c}${big ? " is-8" : ""}"></span>`;

  async function call(method, params) {
    try {
      const res = await host().call(method, params || {});
      return res && typeof res === "object" ? res : { ok: false, error: "No answer" };
    } catch (e) {
      return { ok: false, error: e?.message || String(e) };
    }
  }

  function ensureStyle() {
    let s = document.getElementById("dka-style");
    if (!s) {
      s = document.createElement("style");
      s.id = "dka-style";
      document.head.appendChild(s);
    }
    s.textContent = CSS; // always this copy's CSS, never a stale one
  }

  function unmountPickers() {
    for (const p of state?.pickers || []) {
      try { p.unmount(); } catch { /* gone */ }
    }
    if (state) state.pickers = [];
  }

  // Two clicks instead of a confirm dialog; the button goes back after 3 s.
  function armed(btn, label, run) {
    if (!btn) return;
    let timer = 0;
    const idle = btn.innerHTML;
    btn.addEventListener("click", async () => {
      if (!timer) {
        btn.textContent = label;
        btn.classList.add("is-armed");
        timer = window.setTimeout(() => { btn.innerHTML = idle; btn.classList.remove("is-armed"); timer = 0; }, 3000);
        return;
      }
      window.clearTimeout(timer);
      timer = 0;
      btn.innerHTML = idle;
      btn.classList.remove("is-armed");
      await run();
    });
  }

  function gridTable({ title, sub, cols, minW, head, rows }) {
    const h = head.map(([l, r]) => `<span class="${r ? "dka-r" : ""}">${esc(l)}</span>`).join("");
    const body = rows.length
      ? rows.map((cells) => `<div class="dka-grid" style="grid-template-columns:${cols}">${cells.map((c) => `<span class="${c.cls || ""}" title="${esc(c.t)}">${c.html ?? esc(c.t)}</span>`).join("")}</div>`).join("")
      : `<div class="dka-empty">Nothing yet.</div>`;
    return `<section class="dka-card dka-table">
      <div class="dka-table-head"><b>${esc(title)}</b>${sub ? `<div>${esc(sub)}</div>` : ""}</div>
      <div class="dka-table-scroll"><div class="dka-table-inner" style="min-width:${minW}">
        <div class="dka-grid is-head" style="grid-template-columns:${cols}">${h}</div>${body}
      </div></div></section>`;
  }
  const cell = (t, cls = "") => ({ t: String(t), cls });

  const reloadRules = async () => {
    const st = state;
    const res = await call("get_rules");
    if (state !== st) return;
    st.rules = res;
    render();
  };

  function health() {
    const fails = Object.values(state.checks || {}).filter((c) => !c.ok).length;
    const probs = Object.keys(state.rules?.pick_problems || {}).length;
    if (fails) return { n: fails, c: "red", t: `${fails} can't run` };
    if (probs) return { n: probs, c: "amber", t: `${probs} may not run` };
    if (state.checks) return { n: 0, c: "green", t: "All rules work" };
    return { n: 0, c: "muted", t: "Not checked yet" };
  }

  // ---------------------------------------------------------------- page
  function render() {
    if (!state?.mount) return;
    unmountPickers();
    const m = state.mount;
    const h = state.rules?.ok ? health() : { n: 0 };
    const ver = state.rules?.version || "";
    const tabs = TABS.map(([id, label]) => `<button type="button" role="tab" aria-selected="${state.tab === id}" class="dka-tab${state.tab === id ? " is-on" : ""}" data-tab="${id}">${label}${id === "rules" && h.n ? `<span class="dka-badge">${h.n}</span>` : ""}</button>`).join("");
    m.innerHTML = `<div class="dka">
      <div class="dka-head">
        <div class="dka-head-text">
          <div class="dka-crumb">Settings › LLMs</div>
          <div class="dka-title"><h1>Ducky Auto</h1>${ver ? `<span>plugin ${esc(ver)}</span>` : ""}</div>
          <div class="dka-lede">Picks a model for each message based on what it's about.</div>
        </div>
        <div class="dka-tabs" role="tablist">${tabs}</div>
      </div>
      <div class="dka-body"></div></div>`;
    m.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => { state.tab = b.dataset.tab; render(); }));
    const body = m.querySelector(".dka-body");
    if (state.tab === "analytics") return renderAnalytics(body);
    if (state.tab === "changes") return renderChanges(body);
    if (state.tab === "sharing") return renderSharing(body);
    return renderRules(body);
  }

  const loading = (body) => { body.innerHTML = `<div class="dka-loading">${spin()}Loading…</div>`; };
  function failed(body, msg, retry) {
    body.innerHTML = `<div class="dka-err"><span>${esc(msg || "Couldn't load Ducky Auto: the plugin didn't answer.")}</span><button type="button" class="dka-btn" data-retry>Try again</button></div>`;
    body.querySelector("[data-retry]").addEventListener("click", retry);
  }

  // ---------------------------------------------------------------- Rules
  async function renderRules(body) {
    if (!state.rules) {
      loading(body);
      const st = state;
      const res = await call("get_rules");
      if (state !== st) return;
      st.rules = res;
      if (st.tab === "rules") render();
      return;
    }
    const data = state.rules;
    if (!data.ok) return failed(body, data.error, () => { state.rules = null; render(); });
    const r = data.rules;
    const custom = r.custom || {};
    const order = r.order;
    const all = [...order, "execution", "general"];
    const tr = state.trace?.task ? state.trace : null;
    const kw = tr ? (/^matched "(.+)"$/.exec(tr.why || "") || [])[1] || "" : "";
    const short = tr && !kw && tr.task === "quick";
    let mIdx = tr ? all.indexOf(tr.task) : -1;
    if (tr && mIdx < 0) mIdx = all.length - 1;
    const checks = state.checks || {};

    const rowState = (t, gi) => {
      if (!tr) return "";
      if (gi === mIdx) return "matched";
      if (t === "execution") return "skipped";
      if (gi < mIdx || (short && gi < order.length)) return "skipped";
      return "unreached";
    };
    const rowTag = (t, st) => st === "matched" ? (kw ? `Matched “${kw}”` : short ? "Short question" : "Matched")
      : st === "skipped" ? (t === "execution" ? "Not a tool step" : "No match") : st === "unreached" ? "Not reached" : "";

    const rows = all.map((t, gi) => {
      const fixed = gi >= order.length;
      const st = rowState(t, gi);
      const ck = checks[t];
      const problem = (data.pick_problems || {})[t];
      const words = r.keywords[t] || [];
      const lineIn = tr && gi <= mIdx ? " is-lit" : "";
      const lineOut = tr && gi < mIdx ? " is-lit" : "";
      const chips = words.map((w, k) => `<span class="dka-chip${st === "matched" && w === kw ? " is-hit" : ""}">${esc(w)}<button type="button" data-rm="${k}" aria-label="Remove keyword ${esc(w)}">×</button></span>`).join("");
      const sep = gi === order.length ? `<div class="dka-sep"><div><div class="dka-line${lineIn}"></div></div><div><span class="dka-kicker">Always checked last</span><span></span></div></div>` : "";
      return `${sep}<div class="dka-tl-row ${st ? `is-${st}` : ""}">
        <div class="dka-rail"><div class="dka-line${lineIn}"></div><div class="dka-node">${fixed ? "·" : gi + 1}</div><div class="dka-line${lineOut}"></div></div>
        <div class="dka-tl-body"><div class="dka-task${ck && !ck.ok ? " is-bad" : ""}${state.flash[t] ? " is-flash" : ""}" data-task="${esc(t)}">
          <div class="dka-task-head">
            <span class="dka-task-name">${esc(taskName(t))}</span>
            ${t in custom ? `<span class="dka-yours">yours</span>` : ""}
            ${st ? `<span class="dka-tag">${esc(rowTag(t, st))}</span>` : ""}
            ${ck ? `<span class="dka-check dka-t-${ck.ok ? "green" : "red"}" title="${esc(ck.note)}">${dot(ck.ok ? "green" : "red")}${ck.ok ? "Works" : "Can't run"}</span>` : ""}
            <span class="dka-grow"></span>
            ${fixed ? "" : `<div class="dka-moves">
              <button type="button" class="dka-icon" data-move="-1" aria-label="Move up" title="Check earlier" ${gi === 0 ? "disabled" : ""}>↑</button>
              <button type="button" class="dka-icon" data-move="1" aria-label="Move down" title="Check later" ${gi === order.length - 1 ? "disabled" : ""}>↓</button>
            </div>`}
            ${t in custom ? `<button type="button" class="dka-icon dka-del" data-del aria-label="Delete rule">×</button>` : ""}
          </div>
          <div class="dka-task-body">
            ${fixed ? `<div class="dka-when">${esc(WHEN[t])}</div>`
              : `<div class="dka-chips" data-chips>${chips}<input class="dka-chip-in" data-chip-in aria-label="Add keywords to ${esc(taskName(t))}" placeholder="${words.length ? "Add…" : "Add keywords, e.g. sound*"}" /></div>`}
            <span class="dka-arrow" aria-hidden="true">→</span>
            <div class="dka-picker" data-picker></div>
          </div>
          ${problem && !ck ? `<div class="dka-warn">⚠ ${esc(problem)}: Auto is used until it can run.</div>` : ""}
          ${ck && !ck.ok ? `<div class="dka-fail">✕ ${esc(ck.note || "No model answered its check")}. Auto is used until it can run.</div>` : ""}
        </div></div></div>`;
    }).join("");

    // Step 2: which link of the chain the traced message used.
    const gwLabel = (GATEWAYS.find(([v]) => v === (data.gateway || "")) || GATEWAYS[0])[1];
    let used = -1;
    let pickFailed = false;
    if (tr) {
      const pick = (data.picked || {})[tr.task];
      const ran = tr.gateway ? `${tr.gateway}:${tr.model}` : "";
      used = /login/.test(tr.source || "") ? 0 : pick && ran === pick ? 1 : 2;
      pickFailed = used === 2 && !!pick;
    }
    const tier = tr ? (r.auto_tier || {})[tr.task] || "balanced" : "";
    const chainDefs = [
      ["Your login", "A signed-in tool like Claude Code always wins."],
      ["Your pick", "A model you chose, if it passes its check."],
      ["Auto", used === 2 ? (tier === "stay" ? "Stay: keeps the turn's model." : `Tier ${tier}, from ${gwLabel}: ${tr.model || "no model"}.`)
        : `Picks by the rule's tier (Fast, Balanced, Best or Stay), from ${gwLabel}.`],
    ];
    const chain = chainDefs.map(([title, desc], k) => {
      let st = "";
      let cls = "";
      if (tr) {
        if (k === used) { st = "Used"; cls = " is-used"; }
        else if (k > used) { st = "Skipped"; cls = " is-after"; }
        else { st = k === 1 && pickFailed ? "Can't run" : "Not set"; cls = " is-before"; }
      }
      return `<div class="dka-chain-item"><div class="dka-chain-card${cls}">
        <div class="dka-chain-head"><span class="dka-num">${k + 1}</span><span class="dka-chain-title">${esc(title)}</span>${st ? `<span class="dka-chain-state${st === "Can't run" ? " is-bad" : ""}">${esc(st)}</span>` : ""}</div>
        <span class="dka-chain-desc">${esc(desc)}</span></div>${k < 2 ? `<span class="dka-chain-arrow" aria-hidden="true">→</span>` : ""}</div>`;
    }).join("");

    const hs = health();
    const tools = TOOLS.map(([k, label, busyLabel, tip]) => {
      const busy = !!state.jobs[k];
      return `<button type="button" class="dka-tool" data-job="${k}" ${busy ? "disabled" : ""}>
        <div><div class="dka-tool-label">${esc(busy ? busyLabel : label)}</div><div class="dka-tool-tip">${esc(tip)}</div></div>
        ${busy ? spin() : `<span class="dka-muted">›</span>`}</button>`;
    }).join("");
    const jobs = Object.entries(state.jobs).map(([k, since]) => `<div class="dka-job">
      <div class="dka-job-title">${esc(JOBTXT[k][0])} <span data-since="${since}">${clock(since)}</span></div>
      <div class="dka-job-sub">${esc(JOBTXT[k][1])}</div><div class="dka-job-bar"></div></div>`).join("");
    const res = state.result;
    const result = res ? `<div class="dka-result${res.ok ? "" : " is-bad"}">
      <div class="dka-result-head">${dot(res.ok ? "green" : "red", true)}<span class="dka-result-title">${esc(res.title)}</span><button type="button" class="dka-x" data-dismiss aria-label="Dismiss">×</button></div>
      ${res.sub ? `<div class="dka-result-sub">${esc(res.sub)}</div>` : ""}
      ${(res.lines || []).map((l) => `<div class="dka-rline"><div><span>${esc(l.task)}</span><span class="dka-c-${l.c}">${esc(l.tag)}</span></div><span class="dka-c-${l.c}">${esc(l.value)}</span></div>`).join("")}
      ${(res.sugg || []).map((s, k) => {
        const [kl, kc] = KINDS[s.kind] || [s.kind, "muted"];
        return `<div class="dka-sugg"><div class="dka-sugg-head"><span class="dka-kind dka-t-${kc}">${esc(kl)}</span><span class="dka-sugg-task">${esc(taskName(s.task))}</span></div>
          <div class="dka-sugg-why">${esc(s.why || "")}${s.error ? ` <span class="dka-c-red">${esc(s.error)}</span>` : ""}</div>
          ${s.applied ? `<span class="dka-applied">Applied ✓</span>` : s.action === "info" ? "" : `<button type="button" class="dka-apply" data-apply="${k}" ${s.busy ? "disabled" : ""}>${s.busy ? spin("is-on-accent") : ""}Apply</button>`}</div>`;
      }).join("")}</div>` : "";

    const tryOut = state.trySince
      ? `<div class="dka-small">Finding the rule and checking its model is up… <span data-since="${state.trySince}">${clock(state.trySince)}</span></div>`
      : state.tryErr ? `<div class="dka-small dka-c-red">${esc(state.tryErr)}</div>`
        : tr ? `<div class="dka-trace"><span class="dka-task-pill">${esc(taskName(tr.task))}</span><span class="dka-muted">${esc(tr.why || "")}</span><span class="dka-muted">→</span><span class="dka-mono dka-strong">${esc(tr.model ? `${tr.gateway}:${tr.model}` : "no model")}</span><span class="dka-muted">${esc(tr.source || "")}</span><span class="dka-grow"></span><button type="button" class="dka-btn is-ghost" data-try-clear>Clear</button></div>
            ${tr.note ? `<div class="dka-small dka-c-amber">${esc(tr.note)}</div>` : ""}${tr.ok === false && tr.error ? `<div class="dka-small dka-c-red">${esc(tr.error)}</div>` : ""}`
          : `<div class="dka-small">The path your message takes lights up below.</div>`;

    body.innerHTML = `<div class="dka-col">
      <section class="dka-card dka-try">
        <div class="dka-try-row">
          <input class="dka-input" data-try placeholder="Try a message, e.g. fix the bug in my verse timer" aria-label="Try a message" value="${esc(state.tryText)}" />
          <button type="button" class="dka-btn is-primary" data-try-go ${state.trySince ? "disabled" : ""}>${state.trySince ? spin("is-on-accent") : ""}${state.trySince ? "Checking…" : "Try it"}</button>
        </div>
        <div aria-live="polite">${tryOut}</div>
      </section>
      <div class="dka-split">
        <section class="dka-card dka-flow">
          <div class="dka-step-head">
            <div><div class="dka-kicker">Step 1</div><div class="dka-step-title">Find the rule</div><div class="dka-step-sub">Checked top to bottom. The first rule whose keywords match wins.</div></div>
            <button type="button" class="dka-btn is-raised" data-add-toggle>+ New rule</button>
          </div>
          ${state.adding ? `<div class="dka-add">
            <div class="dka-add-row">
              <input class="dka-input dka-name" data-new-label placeholder="Rule name, e.g. Sound &amp; music" aria-label="Rule name" value="${esc(state.addLabel)}" />
              <input class="dka-input dka-kw" data-new-kw placeholder="Keywords: sound*, music" aria-label="Keywords" value="${esc(state.addKw)}" />
            </div>
            <div class="dka-add-row">
              <span class="dka-hint${state.addErr ? " is-bad" : ""}">${esc(state.addErr || "New rules go to the top. Use word* to match any ending.")}</span>
              <button type="button" class="dka-btn is-ghost" data-add-toggle>Cancel</button>
              <button type="button" class="dka-btn is-primary" data-add>Add rule</button>
            </div></div>` : ""}
          <div class="dka-tl">
            <div class="dka-tl-start"><div><span class="dka-start-dot${tr ? " is-on" : ""}"></span></div><div class="dka-start-label${tr ? " is-on" : ""}">${tr ? `“${esc(tr.prompt)}”` : "Your message"}</div></div>
            ${rows}
          </div>
          <div class="dka-step">
            <div><div class="dka-kicker">Step 2</div><div class="dka-step-title">Pick the model for that rule</div><div class="dka-step-sub">The first one that's set and can run is used.</div></div>
            <div class="dka-chain">${chain}</div>
          </div>
          <div class="dka-step3">
            <div><div class="dka-kicker">Step 3</div><div class="dka-step-title">Switch, or stay on the current model</div>
              <div class="dka-step-sub">Auto switches only if the new model pays for itself within ${esc(r.steps_ahead)} steps. Otherwise it keeps the model the chat is already on. Tool steps always stay.</div></div>
            <div class="dka-outcomes">${OUTCOMES.map(([t, c]) => `<span class="dka-outcome">${dot(c, true)}${esc(t)}</span>`).join("")}</div>
          </div>
        </section>
        <div class="dka-side">
          <section class="dka-card dka-health">
            <div class="dka-health-head"><b>Health</b><span class="dka-status dka-c-${hs.c}">${dot(hs.c, true)}${esc(hs.t)}</span></div>
            ${tools}${jobs}${result}
            <div class="dka-gw"><span>Auto picks from</span><div data-gateway></div></div>
          </section>
          <section class="dka-card">
            <button type="button" class="dka-numbers-btn" data-numbers aria-expanded="${!!state.numbersOpen}">
              <span>${state.numbersOpen ? "▾" : "▸"}</span><span class="dka-grow"><b>Numbers</b><small>Fine-tuning. Most people never need these.</small></span></button>
            ${state.numbersOpen ? `<div class="dka-numbers">
              ${NUMBERS.map(([k, label, help]) => `<label class="dka-number"><div><span>${esc(label)}</span><input class="dka-input" type="number" min="0" data-n="${k}" value="${esc(r[k])}" /></div><span>${esc(help)}</span></label>`).join("")}
              <div class="dka-reset"><span>Puts every rule, keyword and number back the way it shipped. Your own rules are removed.</span>
                <button type="button" class="dka-btn" data-reset>Reset rules to defaults</button></div>
            </div>` : ""}
          </section>
        </div>
      </div></div>`;
    state.flash = {};

    // Try a message
    const tryIn = body.querySelector("[data-try]");
    tryIn.addEventListener("input", () => { state.tryText = tryIn.value; });
    tryIn.addEventListener("keydown", (e) => { if (e.key === "Enter") void runTry(); });
    body.querySelector("[data-try-go]").addEventListener("click", () => void runTry());
    body.querySelector("[data-try-clear]")?.addEventListener("click", () => { state.trace = null; render(); });

    // New rule
    body.querySelectorAll("[data-add-toggle]").forEach((b) => b.addEventListener("click", () => {
      Object.assign(state, { adding: !state.adding, addLabel: "", addKw: "", addErr: "" });
      render();
      state.mount.querySelector("[data-new-label]")?.focus();
    }));
    if (state.adding) {
      const label = body.querySelector("[data-new-label]");
      const kwIn = body.querySelector("[data-new-kw]");
      label.addEventListener("input", () => { state.addLabel = label.value; });
      kwIn.addEventListener("input", () => { state.addKw = kwIn.value; });
      const add = async () => {
        const st = state;
        if (!st.addLabel.trim()) { st.addErr = "Give the rule a name, e.g. Sound & music."; render(); return; }
        const keywords = st.addKw.split(",").map((w) => w.trim()).filter(Boolean);
        const out = await call("add_rule", { label: st.addLabel.trim(), keywords });
        if (state !== st) return;
        if (!out.ok) { st.addErr = out.error || "Couldn't add it."; render(); return; }
        Object.assign(st, { adding: false, addLabel: "", addKw: "", addErr: "", flash: { [out.task]: true } });
        await reloadRules();
      };
      kwIn.addEventListener("keydown", (e) => { if (e.key === "Enter") void add(); });
      body.querySelector("[data-add]").addEventListener("click", () => void add());
    }

    // Rule cards
    body.querySelectorAll(".dka-task").forEach((card) => {
      const t = card.dataset.task;
      card.querySelectorAll("[data-move]").forEach((b) => b.addEventListener("click", async () => {
        const next = [...order];
        const i = next.indexOf(t);
        const j = i + Number(b.dataset.move);
        if (j < 0 || j >= next.length) return;
        [next[i], next[j]] = [next[j], next[i]];
        state.flash = { [t]: true };
        await call("save_rules", { rules_patch: { order: next } });
        await reloadRules();
      }));
      armed(card.querySelector("[data-del]"), "Click again to delete", async () => {
        await call("delete_rule", { task: t });
        await reloadRules();
      });
      const chips = card.querySelector("[data-chips]");
      if (chips) bindChips(chips, t);
      const slot = card.querySelector("[data-picker]");
      let current = (data.logins || {})[t] || (data.picked || {})[t] || "";
      if (host().mountModelPicker) {
        state.pickers.push(host().mountModelPicker(slot, {
          model: current, placeholder: "Auto", logins: true, hideProviders: [PROVIDER],
          effort: (data.effort || {})[t] || "off",
          onChange: (next) => { current = next; void call("set_model", { task: t, model: next }).then(() => reloadRules()); },
          onEffortChange: (effort) => void call("set_model", { task: t, model: current, effort }),
        }));
      } else {
        slot.innerHTML = `<span class="dka-small">${esc(current || "Auto")}: update Ducky to pick here.</span>`;
      }
    });

    // Health
    body.querySelectorAll("[data-job]").forEach((b) => b.addEventListener("click", () => void runJob(b.dataset.job)));
    body.querySelector("[data-dismiss]")?.addEventListener("click", () => { state.result = null; render(); });
    body.querySelectorAll("[data-apply]").forEach((b) => b.addEventListener("click", () => void applySuggestion(Number(b.dataset.apply))));
    const gwEl = body.querySelector("[data-gateway]");
    if (host().mountChoiceDropdown) {
      state.pickers.push(host().mountChoiceDropdown(gwEl, {
        mode: "radio", value: data.gateway || "", "aria-label": "Auto picks from",
        options: GATEWAYS.map(([value, label]) => ({ value, label })),
        onChange: (v) => { data.gateway = v; void call("set_gateway", { gateway: v }).then(() => render()); },
      }));
    }

    // Numbers
    body.querySelector("[data-numbers]").addEventListener("click", () => { state.numbersOpen = !state.numbersOpen; render(); });
    body.querySelectorAll("[data-n]").forEach((inp) => inp.addEventListener("change", () => {
      const v = parseInt(inp.value.replace(/[, ]/g, ""), 10);
      if (!Number.isFinite(v) || v < 0) return;
      r[inp.dataset.n] = v;
      void call("save_rules", { rules_patch: { [inp.dataset.n]: v } });
    }));
    armed(body.querySelector("[data-reset]"), "Click again to reset", async () => {
      await call("reset_rules");
      state.checks = null;
      state.trace = null;
      await reloadRules();
    });
  }

  // Keyword chips: comma, Enter or leaving the field adds; Backspace on an empty field removes the last.
  function bindChips(box, t) {
    const input = box.querySelector("[data-chip-in]");
    const words = () => state.rules.rules.keywords[t] || [];
    const save = (next) => {
      state.rules.rules.keywords[t] = next;
      void call("save_rules", { rules_patch: { keywords: { [t]: next } } });
      const focus = document.activeElement === input;
      const fresh = document.createElement("div");
      fresh.innerHTML = `<div class="dka-chips" data-chips>${next.map((w, k) => `<span class="dka-chip">${esc(w)}<button type="button" data-rm="${k}" aria-label="Remove keyword ${esc(w)}">×</button></span>`).join("")}<input class="dka-chip-in" data-chip-in aria-label="${esc(input.getAttribute("aria-label"))}" placeholder="${next.length ? "Add…" : "Add keywords, e.g. sound*"}" /></div>`;
      const nb = fresh.firstElementChild;
      box.replaceWith(nb);
      bindChips(nb, t);
      if (focus) nb.querySelector("[data-chip-in]").focus();
    };
    const commit = () => {
      const add = input.value.split(",").map((w) => w.trim().toLowerCase()).filter(Boolean);
      input.value = "";
      const cur = words();
      const next = [...cur, ...add.filter((w, i) => !cur.includes(w) && add.indexOf(w) === i)];
      if (next.length !== cur.length) save(next);
    };
    box.addEventListener("click", (e) => { if (e.target === box) input.focus(); });
    box.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => {
      save(words().filter((_w, k) => k !== Number(b.dataset.rm)));
    }));
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === ",") { e.preventDefault(); commit(); }
      else if (e.key === "Backspace" && !input.value && words().length) save(words().slice(0, -1));
    });
    input.addEventListener("blur", () => { if (input.value.trim()) commit(); });
  }

  async function runTry() {
    const st = state;
    const prompt = (st.tryText || "").trim();
    if (!prompt) { Object.assign(st, { tryErr: "Type a message first.", trace: null }); render(); return; }
    if (st.trySince) return;
    Object.assign(st, { trySince: Date.now(), tryErr: "", trace: null });
    render();
    const res = await call("route", { prompt });
    if (state !== st) return;
    st.trySince = 0;
    if (!res.task) st.tryErr = res.error || "Couldn't route it.";
    else st.trace = { ...res, prompt };
    if (st.tab === "rules") render();
  }

  async function runJob(kind) {
    const st = state;
    if (st.jobs[kind]) return;
    st.jobs[kind] = Date.now();
    if (st.result?.kind === kind) st.result = null;
    render();
    const before = { ...(st.rules?.picked || {}) };
    let result;
    if (kind === "check") {
      const res = await call("check_routes");
      const rows = res.routes || [];
      st.checks = {};
      for (const row of rows) st.checks[row.task] = { ok: !!row.ok, note: row.note || "" };
      const bad = rows.filter((x) => !x.ok).map((x) => taskName(x.task));
      result = rows.length ? {
        kind, ok: !bad.length, title: bad.length ? `No working model for ${bad.join(", ")}` : "All set.",
        sub: bad.length ? "Auto covers it for now. Results are also on each rule." : "Every rule has a model that answered.",
        lines: rows.map((x) => ({ task: taskName(x.task), c: x.ok ? "fg" : "red", tag: x.ok ? "✓" : "✕",
          value: x.ok ? `${x.gateway ? `${x.gateway}:` : ""}${x.model || ""}` : x.note || "no model answered" })),
      } : { kind, ok: false, title: "Couldn't check", sub: res.error || res.detail || "" };
    } else if (kind === "setup") {
      const res = await call("setup");
      const kept = Object.keys(res.kept_your_picks || {}).map(taskName).join(", ");
      const plan = Object.entries(res.plan || {});
      result = res.ok ? {
        kind, ok: true, title: `Set up ${plan.length} rule${plan.length === 1 ? "" : "s"}`,
        sub: [kept && `Kept your picks for ${kept}.`, res.note].filter(Boolean).join(" "),
        lines: plan.map(([t, mdl]) => ({ task: taskName(t), value: mdl, c: "fg", tag: before[t] ? "replaced" : "new" })),
      } : { kind, ok: false, title: "Setup didn't finish", sub: res.error || "" };
      if (res.ok) st.flash = Object.fromEntries(plan.map(([t]) => [t, true]));
    } else {
      const res = await call("tune", { apply: false });
      const sugg = res.suggestions || [];
      const n = sugg.filter((s) => s.action !== "info").length;
      result = res.ok ? {
        kind, ok: true, title: n ? `${n} suggested change${n === 1 ? "" : "s"}` : "Nothing to change",
        sub: res.note || "Based on the last 500 steps on this PC.", sugg,
      } : { kind, ok: false, title: "Couldn't read the steps", sub: res.error || "" };
    }
    if (state !== st) return;
    delete st.jobs[kind];
    st.result = result;
    if (kind === "setup") return reloadRules();
    if (st.tab === "rules") render();
  }

  async function applySuggestion(k) {
    const st = state;
    const s = st.result?.sugg?.[k];
    if (!s || s.busy || s.applied) return;
    s.busy = true;
    render();
    const res = await call("tune", { apply: true, task: s.task, kind: s.kind });
    if (state !== st) return;
    s.busy = false;
    if ((res.applied || []).length) { s.applied = true; st.flash = { [s.task]: true }; }
    else s.error = res.error || "No other model answered its check.";
    await reloadRules();
  }

  // ---------------------------------------------------------------- Analytics
  function sankey(steps) {
    const rows = steps.filter((r) => r.task);
    if (!rows.length) return { html: `<div class="dka-empty">Nothing yet. Steps show up here once you chat with Auto on.</div>`, bind: () => {} };
    const H = 380, GAP = 10;
    const keyOf = [(r) => r.task, (r) => r.decision || "–", (r) => r.model || "none"];
    const cols = keyOf.map((f, ci) => {
      const counts = new Map();
      for (const r of rows) counts.set(f(r), (counts.get(f(r)) || 0) + 1);
      return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([id, v], i) => ({
        k: `${ci}:${id}`, id, v,
        label: ci === 0 ? taskName(id) : ci === 1 ? (DECISIONS[id] || [id])[0] : id,
        c: ci === 1 ? (DECISIONS[id] || [0, "muted"])[1] : PALETTE[(i + ci) % PALETTE.length],
        mono: ci === 2,
      }));
    });
    cols.forEach((col) => {
      col.sc = (H - GAP * (col.length - 1)) / rows.length;
      let y = 0;
      for (const n of col) { n.y = y; n.h = Math.max(2, n.v * col.sc); y += n.h + GAP; n.out = n.y; n.in = n.y; }
    });
    const sc = Math.min(...cols.map((c) => c.sc));
    const X = [[10, 495], [505, 990]];
    const links = [];
    for (const ci of [0, 1]) {
      for (const a of cols[ci]) {
        for (const b of cols[ci + 1]) {
          const v = rows.filter((r) => keyOf[ci](r) === a.id && keyOf[ci + 1](r) === b.id).length;
          if (!v) continue;
          const wa = v * cols[ci].sc, wb = v * cols[ci + 1].sc;
          const y0 = a.out, y1 = b.in;
          a.out += wa; b.in += wb;
          const [x0, x1] = X[ci], xm = (x0 + x1) / 2;
          const w = Math.min(wa, wb, v * sc * 2);
          links.push({ k: `${a.k}>${b.k}`, a: a.k, b: b.k, c: ci === 0 ? a.c : b.c,
            txt: `${a.label} → ${b.label}: ${v} step${v === 1 ? "" : "s"}`,
            d: `M${x0},${y0} C${xm},${y0} ${xm},${y1} ${x1},${y1} L${x1},${y1 + wb} C${xm},${y1 + wb} ${xm},${y0 + wa} ${x0},${y0 + wa} Z`, w });
        }
      }
    }
    const nodes = cols.flatMap((col, ci) => col.map((n) => ({ ...n, ci })));
    const paths = links.map((l, i) => `<path class="dka-band" data-link="${i}" d="${l.d}" style="fill:var(--${l.c})" fill-opacity=".32"></path>`).join("");
    const bars = nodes.map((n, i) => {
      const left = n.ci === 0 ? "0px" : n.ci === 1 ? "calc(50% - 5px)" : "calc(100% - 10px)";
      const lab = n.ci === 0 ? "left:16px" : n.ci === 1 ? "left:calc(50% + 10px)" : "right:16px;justify-content:flex-end";
      return `<div class="dka-sk-node dka-b-${n.c}" data-node="${i}" style="left:${left};top:${n.y}px;height:${n.h}px"></div>
        <div class="dka-sk-label" data-node="${i}" style="${lab};top:${n.y + n.h / 2}px"><span${n.mono ? ` class="dka-mono"` : ""}><b>${esc(n.label)}</b> <span class="dka-muted">${n.v}</span></span></div>`;
    }).join("");
    const html = `<div class="dka-sk-scroll"><div class="dka-sk-inner">
      <div class="dka-sk-cols"><span>Rule</span><span>Decision</span><span>Model</span></div>
      <div class="dka-sk-area" data-sk style="height:${H}px"><svg viewBox="0 0 1000 ${H}" preserveAspectRatio="none" aria-hidden="true">${paths}</svg>${bars}</div>
    </div></div>`;
    const bind = (root) => {
      const area = root.querySelector("[data-sk]");
      const cap = root.querySelector("[data-cap]");
      if (!area || !cap) return;
      const show = (hl) => {
        const on = (l) => !hl || l.k === hl || l.a === hl || l.b === hl;
        const lit = new Set(hl ? [hl, ...links.filter(on).flatMap((l) => [l.a, l.b])] : []);
        area.querySelectorAll("[data-link]").forEach((p) => { const l = links[+p.dataset.link]; p.setAttribute("fill-opacity", on(l) ? (hl ? ".6" : ".32") : ".06"); });
        area.querySelectorAll("[data-node]").forEach((el) => { el.style.opacity = !hl || lit.has(nodes[+el.dataset.node].k) ? "1" : ".3"; });
        const link = links.find((l) => l.k === hl);
        const node = nodes.find((n) => n.k === hl);
        cap.textContent = link ? link.txt : node ? `${node.label}: ${node.v} steps` : "Hover a band or a bar for numbers.";
        cap.classList.toggle("is-on", !!hl);
      };
      area.addEventListener("mouseover", (e) => {
        const el = e.target.closest?.("[data-link],[data-node]");
        if (!el) return;
        show(el.dataset.link != null ? links[+el.dataset.link].k : nodes[+el.dataset.node].k);
      });
      area.addEventListener("mouseleave", () => show(null));
    };
    return { html, bind };
  }

  async function renderAnalytics(body) {
    loading(body);
    const st = state;
    const res = await call("analytics", { limit: 500 });
    if (state !== st || st.tab !== "analytics") return;
    if (!res.ok) return failed(body, res.error, () => render());
    const s = res.summary || {};
    const t = s.totals || {};
    const sv = s.savings || {};
    const tiles = [
      [num(t.steps), "steps routed", "fg"], [num(t.switches), "model switches", "fg"], [num(t.kept), "kept (cheaper to stay)", "fg"],
      [`${num(t.errors)} · ${pct(t.error_rate)}`, "errors", t.errors ? "red" : "fg"],
      [num(t.probe_failures), "failed model checks", t.probe_failures ? "amber" : "fg"],
      [usd(t.cost_usd), t.priced_steps ? `cost (${num(t.priced_steps)} priced steps)` : "cost", "fg"],
      [sv.saved_usd == null ? "no prices yet" : usd(sv.saved_usd), sv.baseline_model ? `saved vs. ${sv.baseline_model}` : "saved", sv.saved_usd == null ? "muted" : "green"],
      [sv.cache_share == null ? "—" : pct(sv.cache_share), "input read from cache", "fg"],
    ].map(([v, l, c]) => `<div class="dka-tile"><b class="dka-c-${c}">${esc(v)}</b><span>${esc(l)}</span></div>`).join("");
    const errCell = (e, rate) => cell(`${num(e || 0)} · ${pct(rate || 0)}`, `dka-r${e ? " dka-c-red dka-strong" : ""}`);
    const byModel = Object.entries(s.by_model || {}).sort((a, b) => b[1].steps - a[1].steps).map(([k, v]) => [
      cell(k, "dka-mono"), cell(num(v.steps), "dka-r"), errCell(v.errors, v.error_rate), cell(fmtK(v.input), "dka-r"),
      cell(fmtK(v.output), "dka-r"), cell(fmtK(v.cached), "dka-r"), cell(v.cost_usd ? usd(v.cost_usd) : "—", "dka-r"), cell(secs(v.avg_ms), "dka-r")]);
    const byTask = Object.entries(s.by_task || {}).sort((a, b) => b[1].steps - a[1].steps).map(([k, v]) => [
      cell(taskName(k)), cell(num(v.steps), "dka-r"), errCell(v.errors, v.error_rate), cell(fmtK(v.avg_input), "dka-r"), cell(fmtK(v.avg_output), "dka-r"),
      cell(v.avg_tool_calls ?? "–", "dka-r"), cell(secs(v.avg_first_token_ms), "dka-r"), cell(secs(v.avg_ms), "dka-r")]);
    const recent = (res.steps || []).slice(0, 40).map((r) => {
      const u = r.usage || {};
      const fc = (r.failed || []).length;
      return [cell(ago(r.ts), "dka-muted"), cell(taskName(r.task)), cell(`${r.gateway || ""}:${r.model || ""}`, "dka-mono"),
        cell(r.decision || "", "dka-muted"), cell(fmtK(u.input_tokens ?? u.prompt_tokens), "dka-r"), cell(fmtK(u.output_tokens ?? u.completion_tokens), "dka-r"),
        cell(fc, `dka-r ${fc ? "dka-c-red dka-strong" : "dka-muted"}`), cell(secs(r.ms), "dka-r"),
        cell(r.error ? String(r.error).slice(0, 120) : "—", r.error ? "dka-c-red" : "dka-muted")];
    });
    const sk = sankey(res.steps || []);
    body.innerHTML = `<div class="dka-col">
      <div class="dka-bar-row"><b>Last ${num(t.steps || 0)} steps</b><button type="button" class="dka-btn" data-refresh>Refresh</button><button type="button" class="dka-btn" data-clear>Clear log</button></div>
      <div class="dka-tiles">${tiles}</div>
      <section class="dka-card dka-sk">
        <div class="dka-sk-head"><div><b>How steps were routed</b><div class="dka-small">Rule → what Auto decided → the model that answered.</div></div>
          <span class="dka-sk-cap" data-cap>Hover a band or a bar for numbers.</span></div>
        ${sk.html}
      </section>
      ${gridTable({ title: "Per model", cols: "minmax(200px,2fr) 60px 100px 70px 70px 70px 70px 80px", minW: "780px",
        head: [["Model"], ["Steps", 1], ["Errors · rate", 1], ["In", 1], ["Out", 1], ["Cached", 1], ["Cost", 1], ["Avg time", 1]], rows: byModel })}
      ${gridTable({ title: "Per task", cols: "minmax(140px,1.5fr) 60px 100px 70px 70px 60px 90px 80px", minW: "700px",
        head: [["Task"], ["Steps", 1], ["Errors · rate", 1], ["Avg in", 1], ["Avg out", 1], ["Tools", 1], ["First token", 1], ["Avg time", 1]], rows: byTask })}
      ${gridTable({ title: "Recent steps", sub: "This PC only. Prompts are never stored.", cols: "80px minmax(110px,1fr) minmax(190px,1.6fr) minmax(120px,1.2fr) 60px 60px 60px 60px minmax(160px,1.6fr)", minW: "1000px",
        head: [["When"], ["Task"], ["Model"], ["Decision"], ["In", 1], ["Out", 1], ["Failed", 1], ["Time", 1], ["Error"]], rows: recent })}
    </div>`;
    sk.bind(body);
    body.querySelector("[data-refresh]").addEventListener("click", () => render());
    armed(body.querySelector("[data-clear]"), "Click again to clear", async () => { await call("analytics_clear"); render(); });
  }

  // ---------------------------------------------------------------- Changes
  async function renderChanges(body) {
    loading(body);
    const st = state;
    const res = await call("analytics", { limit: 1 });
    if (state !== st || st.tab !== "changes") return;
    if (!res.ok) return failed(body, res.error, () => render());
    const list = res.adjustments || [];
    const rows = list.map((a) => `<div class="dka-change">
      <span title="${esc(new Date((a.when || 0) * 1000).toLocaleString())}">${esc(ago(a.when))}</span>
      <span class="dka-kind dka-t-${BY[a.by] || "muted"}">${esc(a.by)}</span>
      <div class="dka-change-what"><div><span>${esc(taskName(a.task))}</span><span class="dka-before">${esc(a.before || "Auto")}</span><span class="dka-muted">→</span><span class="dka-after">${esc(a.after || "Auto")}</span></div>
        ${a.why ? `<span>${esc(a.why)}</span>` : ""}</div></div>`).join("");
    body.innerHTML = `<div class="dka-col" style="gap:12px">
      <div class="dka-small">Every change to the rules and models: by you, an agent, Set up for me or the tuner.</div>
      ${list.length ? `<div class="dka-card dka-changes">${rows}</div>` : `<div class="dka-note-card dka-muted">Nothing yet.</div>`}
    </div>`;
  }

  // ---------------------------------------------------------------- Sharing
  async function renderSharing(body) {
    loading(body);
    const st = state;
    const res = await call("share_status");
    if (state !== st || st.tab !== "sharing") return;
    if (!res.ok) return failed(body, res.error, () => render());
    const on = !!res.enabled;
    const props = Object.entries(res.preview?.props || {}).map(([k, v]) => `<div class="dka-grid"><span class="dka-muted">${esc(k)}</span><span>${esc(v === null ? "null" : String(v))}</span></div>`).join("");
    body.innerHTML = `<div class="dka-col">
      <div class="dka-card dka-share">
        <div><b>Share anonymous usage</b><div class="dka-small" style="margin-top:2px">Off unless you turn it on.</div></div>
        <button type="button" class="dka-switch" role="switch" aria-checked="${on}" aria-label="Share anonymous usage" data-share><span></span></button>
      </div>
      <div class="dka-explain">Ducky Auto is open source. With sharing on, it sends the few numbers below for each step, so the default rules get better for everyone. <b>Never your messages, files or account.</b> The id is random for this install only.</div>
      <div class="dka-share-status">
        <span class="dka-status dka-c-${on ? "green" : "muted"}" style="font-size:13px;font-weight:700">${dot(on ? "green" : "muted", true)}${on ? "On" : "Off"}</span>
        <span>sent <b>${num(res.sent || 0)}</b> steps</span>
        <span><b>${num(res.waiting || 0)}</b> waiting</span>
        ${res.last_error ? `<span class="dka-c-red">${esc(res.last_error)}</span>` : ""}
        <span class="dka-grow"></span>
        <span>To <span class="dka-mono dka-c-fg">${esc(res.to || "")}</span></span>
      </div>
      <section class="dka-card dka-table dka-props">
        <div class="dka-table-head"><b>Exactly what one step sends</b></div>
        <div class="dka-table-inner"><div class="dka-grid is-head"><span>Field</span><span>Value</span></div>${props || `<div class="dka-empty">Nothing yet.</div>`}</div>
      </section>
    </div>`;
    body.querySelector("[data-share]").addEventListener("click", (e) => {
      const next = e.currentTarget.getAttribute("aria-checked") !== "true";
      e.currentTarget.setAttribute("aria-checked", String(next));
      host().prefs.set({ share_analytics: next });
      window.setTimeout(render, 300);
    });
  }

  // ---------------------------------------------------------------- slot
  function open(mount) {
    ensureStyle();
    if (state?.mount === mount) return;
    close();
    state = {
      mount, tab: "rules", rules: null, pickers: [], jobs: {}, checks: null, result: null,
      trace: null, tryText: "", trySince: 0, tryErr: "", adding: false, addLabel: "", addKw: "", addErr: "",
      numbersOpen: false, flash: {}, timer: 0,
    };
    if (!host()?.call) {
      mount.innerHTML = `<div class="dka"><div class="dka-note-card">Update Ducky to see Ducky Auto's rules and analytics here.</div></div>`;
      return;
    }
    // One clock for every running timer on the page.
    state.timer = window.setInterval(() => {
      state?.mount?.querySelectorAll("[data-since]").forEach((el) => { el.textContent = clock(Number(el.dataset.since)); });
    }, 250);
    render();
  }

  function close() {
    unmountPickers();
    if (state?.timer) window.clearInterval(state.timer);
    if (state?.mount) state.mount.innerHTML = "";
    state = null;
  }

  const onSlot = (ev) => {
    const d = ev.detail || {};
    if (d.surface !== "settings") return;
    if (d.open && d.providerId === PROVIDER && d.mount) open(d.mount);
    else if (state) close();
  };
  window.addEventListener("ducky:llm-slot", onSlot);
  // The page may already be open when this script loads.
  const existing = document.querySelector(`[data-ducky-llm-slot="settings"][data-provider="${PROVIDER}"]`);
  if (existing) open(existing);

  window.__duckyPluginBootCleanups = window.__duckyPluginBootCleanups || {};
  window.__duckyPluginBootCleanups[PID] = () => {
    window.removeEventListener("ducky:llm-slot", onSlot);
    close();
    document.getElementById("dka-style")?.remove();
  };
})();
