// Loads ui/settings.js in jsdom with a fake host and checks every tab draws.
// node tests/page_check.cjs ui/settings.js <folder whose node_modules has jsdom>
const fs = require("fs");
const { JSDOM } = require(require.resolve("jsdom", { paths: [process.argv[3] || process.cwd()] }));
const assert = require("assert");
const same = (a, b, msg) => assert.strictEqual(JSON.stringify(a), JSON.stringify(b), msg);

const dom = new JSDOM(`<!doctype html><body></body>`, { runScripts: "outside-only" });
const { window } = dom;
const calls = [];
const pickers = [];
const rules = {
  ok: true, version: "1.13.0", gateway: "anthropic", effort: { coding: "high" }, pick_problems: {},
  picked: { planning: "anthropic:claude-opus-5-5" }, logins: { planning: "claude_code:claude-opus-5-5" },
  rules: { order: ["coding", "planning"], keywords: { coding: ["code"], planning: ["plan*"] }, custom: {},
           examples: { coding: ["make the door open"] }, long_context: 100000, match_confidence: 35, learn: true,
           short_question_chars: 90, small_context: 8000, steps_ahead: 3 },
};
const answers = {
  get_rules: rules,
  route: { ok: true, task: "planning", why: 'matched "plan*"', source: "your pick, on your Claude Code login (the whole turn runs there)",
           gateway: "claude_code", model: "claude-opus-5-5", note: "", failed: [] },
  check_routes: { ok: false, routes: [{ task: "coding", ok: false, note: "no key" }, { task: "planning", ok: true, model: "claude-opus-5-5" }] },
  tune: { ok: true, suggestions: [{ kind: "slow", task: "coding", action: "replace", why: "slow" }], applied: [{ task: "coding" }] },
  analytics: { ok: true, summary: { totals: { steps: 2, errors: 1, error_rate: 0.5 }, by_model: { "gemini:f": { steps: 2, errors: 1, error_rate: 0.5 } }, by_task: {}, savings: {} },
               steps: [{ ts: 1, task: "coding", decision: "switched", gateway: "gemini", model: "f", usage: { input_tokens: 5 }, error: "boom" }],
               adjustments: [{ when: 1, by: "you", task: "coding", before: "Auto", after: "openai:x", why: "" }] },
  share_status: { ok: true, enabled: false, sent: 0, waiting: 0, to: "https://x", preview: { props: { task: "coding" } } },
};
window.__duckyPluginHost = {
  forPlugin: () => ({
    call: async (m, p) => { calls.push([m, p]); return answers[m] || { ok: true }; },
    prefs: { set: (p) => calls.push(["prefs", p]) },
    mountModelPicker: (el, opts) => { pickers.push(opts); el.textContent = opts.model || opts.placeholder; return { unmount() {} }; },
    mountChoiceDropdown: (el, opts) => { el.textContent = opts.value; return { unmount() {} }; },
  }),
};
window.eval(fs.readFileSync(process.argv[2] || "ui/settings.js", "utf8"));

const mount = window.document.createElement("div");
window.document.body.appendChild(mount);
const tick = () => new Promise((r) => setTimeout(r, 20));
const $ = (s) => mount.querySelector(s);
(async () => {
  window.dispatchEvent(new window.CustomEvent("ducky:llm-slot", { detail: { surface: "settings", open: true, providerId: "ducky_auto", mount } }));
  await tick();
  same([...mount.querySelectorAll(".dka-tab")].map((b) => b.dataset.tab), ["rules", "analytics", "changes", "sharing"]);
  assert.ok(mount.textContent.includes("plugin 1.13.0"), "version in the header");
  assert.strictEqual(mount.querySelectorAll(".dka-task").length, 5, "coding, planning, long chats, tool steps, everything else");
  assert.ok($('[data-task="long"]').textContent.includes("over 100k tokens"), "long chats rule");
  assert.strictEqual(pickers.length, 5);
  assert.strictEqual(pickers.find((p) => p.model === "claude_code:claude-opus-5-5").logins, true);
  pickers[0].onEffortChange("low");
  same(calls.at(-1), ["set_model", { task: "coding", model: "", effort: "low" }]);

  // Keyword chips: Enter adds, × removes.
  const chipIn = $('[data-task="coding"] [data-chip-in]');
  chipIn.value = "Bug, fix*";
  chipIn.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  same(calls.at(-1), ["save_rules", { rules_patch: { keywords: { coding: ["code", "bug", "fix*"] } } }]);
  $('[data-task="coding"] [data-rm="0"]').click();
  same(calls.at(-1), ["save_rules", { rules_patch: { keywords: { coding: ["bug", "fix*"] } } }]);

  // Example chips: a whole line, commas kept.
  const exIn = $('[data-task="coding"] [data-chips="examples"] [data-chip-in]');
  exIn.value = "Fix the timer, it skips";
  exIn.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  same(calls.at(-1), ["save_rules", { rules_patch: { examples: { coding: ["make the door open", "fix the timer, it skips"] } } }]);

  // Learn from results switch.
  $("[data-numbers]").click();
  assert.strictEqual($("[data-learn]").getAttribute("aria-checked"), "true");
  $("[data-learn]").click();
  same(calls.at(-1), ["save_rules", { rules_patch: { learn: false } }]);
  assert.strictEqual($("[data-learn]").getAttribute("aria-checked"), "false");

  // Try a message lights the path.
  const tryIn = $("[data-try]");
  tryIn.value = "plan a boss fight";
  tryIn.dispatchEvent(new window.Event("input"));
  $("[data-try-go]").click();
  await tick();
  assert.ok($('[data-task="planning"]').closest(".dka-tl-row").classList.contains("is-matched"), "planning matched");
  assert.ok($('[data-task="coding"]').closest(".dka-tl-row").classList.contains("is-skipped"), "coding skipped");
  assert.ok($(".dka-chip.is-hit").textContent.startsWith("plan*"), "keyword lit");
  assert.ok($(".dka-chain-card.is-used").textContent.includes("Your login"), "login used");

  // An example match tags the rule and lights the example.
  answers.route = { ok: true, task: "coding", why: 'like "make the door open" (62%)', source: "auto", gateway: "gemini", model: "f", note: "", failed: [] };
  $("[data-try-go]").click();
  await tick();
  assert.ok($('[data-task="coding"]').textContent.includes("Like “make the door open” 62%"), "example tag");
  assert.strictEqual($('[data-chips="examples"] .dka-chip.is-hit').textContent.replace("×", ""), "make the door open", "example lit");

  // Health tools.
  $('[data-job="check"]').click();
  await tick();
  assert.ok(mount.textContent.includes("1 can't run"), "health status");
  assert.strictEqual($(".dka-badge").textContent, "1", "rules tab badge");
  $('[data-job="tune"]').click();
  await tick();
  $('[data-apply="0"]').click();
  await tick();
  same(calls.filter((c) => c[0] === "tune").at(-1), ["tune", { apply: true, task: "coding", kind: "slow" }]);
  assert.ok(mount.textContent.includes("Applied ✓"));

  $('[data-tab="analytics"]').click();
  await tick();
  assert.ok(mount.textContent.includes("gemini:f") && mount.textContent.includes("boom"), "analytics tables");
  assert.ok($(".dka-sk-area path.dka-band"), "sankey bands");
  $('[data-tab="changes"]').click();
  await tick();
  assert.ok(mount.textContent.includes("openai:x"), "changes list");
  $('[data-tab="sharing"]').click();
  await tick();
  assert.strictEqual($("[data-share]").getAttribute("aria-checked"), "false");
  $("[data-share]").click();
  same(calls.find((c) => c[0] === "prefs"), ["prefs", { share_analytics: true }]);

  window.dispatchEvent(new window.CustomEvent("ducky:llm-slot", { detail: { surface: "settings", open: false, providerId: "", mount: null } }));
  assert.strictEqual(mount.innerHTML, "");
  console.log("ducky-auto page ok");
  process.exit(0);
})().catch((e) => { console.error(e); process.exit(1); });
