let currentView = "instagram";
let currentContactId = null;
let currentApprovalId = null;
let lastState = null;

const $ = (id) => document.getElementById(id);

const PERSONAL_TARGET_PRESETS = [
  { label: "☕ Coffee Date", value: "Ask her out for a coffee date smoothly" },
  { label: "🌹 Propose for Date", value: "Propose a dinner / evening date charmingly" },
  { label: "❤️ Say I Love You", value: "Say I love you genuinely and memorably" },
  { label: "🎬 Movie Plan", value: "Make a fun movie + hangout plan this weekend" },
  { label: "📱 Ask for Number", value: "Smoothly transition to WhatsApp / get her phone number" },
];

const LINKEDIN_TARGET_PRESETS = [
  { label: "📞 Schedule Call", value: "Schedule a 15-minute intro call to discuss the role" },
  { label: "💼 Ask for Referral", value: "Politely ask for a referral with a crisp pitch" },
  { label: "📄 Share Resume", value: "Offer to share updated resume & discuss fit" },
  { label: "☕ Coffee Chat", value: "Request a brief networking coffee chat" },
];

function showToast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  setTimeout(() => t.classList.add("hidden"), 3200);
}

async function api(url, opts = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function setTheme(view) {
  document.body.classList.remove("theme-instagram", "theme-whatsapp", "theme-linkedin");
  if (["instagram", "whatsapp", "linkedin"].includes(view)) {
    document.body.classList.add(`theme-${view}`);
  } else {
    document.body.classList.add("theme-instagram");
  }
}

function renderTargetPresets(platform, currentTarget) {
  const container = $("targetPresetChips");
  container.innerHTML = "";
  const list = platform === "linkedin" ? LINKEDIN_TARGET_PRESETS : PERSONAL_TARGET_PRESETS;
  list.forEach((p) => {
    const btn = document.createElement("button");
    btn.className = "preset-chip";
    if ((currentTarget || "").toLowerCase() === p.value.toLowerCase()) {
      btn.classList.add("active");
    }
    btn.textContent = p.label;
    btn.onclick = async () => {
      $("chatTargetInput").value = p.value;
      await saveStrategy();
    };
    container.appendChild(btn);
  });
}

function updateExecuteTargetButton(target, platform) {
  const clean = (target || "").trim();
  if (clean) {
    const short = clean.length > 34 ? clean.slice(0, 34) + "..." : clean;
    $("btnPropose").textContent = `✦ Execute Target: ${short}`;
  } else {
    $("btnPropose").textContent =
      platform === "linkedin" ? "✦ Execute Target: Next Step / Call" : "✦ Propose / Execute Target Now";
  }
}

async function saveStrategy() {
  if (!currentContactId) return showToast("Select a contact first.");
  const chat_style = $("chatStyleInput").value.trim();
  const chat_target = $("chatTargetInput").value.trim();
  await api(`/api/contacts/${currentContactId}`, {
    method: "PUT",
    body: JSON.stringify({ chat_style, chat_target }),
  });
  updateExecuteTargetButton(chat_target, currentView);
  renderTargetPresets(currentView, chat_target);
  showToast("Chat Style & Target saved! Gemini will follow this now.");
}

async function switchView(view) {
  currentView = view;
  setTheme(view);

  document.querySelectorAll(".nav-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.view === view);
  });

  const isChat = ["instagram", "whatsapp", "linkedin"].includes(view);
  $("chatWorkspace").classList.toggle("hidden", !isChat);
  $("intelPanel").classList.toggle("hidden", !isChat);
  $("databaseView").classList.toggle("hidden", view !== "database");
  $("settingsView").classList.toggle("hidden", view !== "settings");

  if (isChat) {
    const titles = {
      instagram: "Instagram Mode",
      whatsapp: "WhatsApp Mode",
      linkedin: "LinkedIn Mode",
    };
    $("platformTitle").textContent = titles[view];
    $("intelTitle").textContent = view === "linkedin" ? "LINKEDIN PROFILE INTEL" : "PROFILE INTEL";
    $("btnScanProfile").classList.toggle("hidden", view === "whatsapp");

    await loadContactsForPlatform(view);
  } else if (view === "database") {
    await loadDatabaseView();
  } else if (view === "settings") {
    await loadSettingsView();
  }
}

async function loadContactsForPlatform(platform) {
  const data = await api(`/api/contacts?platform=${platform}`);
  const sel = $("contactSelector");
  sel.innerHTML = "";
  if (!data.contacts.length) {
    sel.innerHTML = `<option value="">No whitelisted contacts</option>`;
    currentContactId = null;
    $("chatStyleInput").value = "";
    $("chatTargetInput").value = "";
    renderTargetPresets(platform, "");
    updateExecuteTargetButton("", platform);
    $("chatFeed").innerHTML = `<div class="empty-state">Click "+ Add Contact" to whitelist a ${platform} chat.</div>`;
    return;
  }
  data.contacts.forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = `${c.name} (${c.handle})`;
    sel.appendChild(opt);
  });
  currentContactId = Number(sel.value);
  await loadContactDetail(currentContactId);
}

function renderTags(containerId, csvStr, accent = false) {
  const el = $(containerId);
  el.innerHTML = "";
  const items = (csvStr || "").split(",").map((s) => s.trim()).filter(Boolean);
  if (!items.length) {
    el.innerHTML = `<span class="muted-label">Not scanned yet</span>`;
    return;
  }
  items.forEach((item) => {
    const span = document.createElement("span");
    span.className = `tag ${accent ? "accent" : ""}`;
    span.textContent = item;
    el.appendChild(span);
  });
}

async function loadContactDetail(cid) {
  if (!cid) return;
  const ctx = await api(`/api/contacts/${cid}`);
  const c = ctx.contact;
  const p = ctx.profile_intel || {};

  // Strategy fields (Custom Chat Style & Target)
  $("chatStyleInput").value = c.chat_style || "";
  $("chatTargetInput").value = c.chat_target || "";
  renderTargetPresets(c.platform, c.chat_target || "");
  updateExecuteTargetButton(c.chat_target || "", c.platform);

  // Persona active button
  document.querySelectorAll(".persona-pill").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.persona === c.persona);
  });

  // Render chat bubbles
  const feed = $("chatFeed");
  feed.innerHTML = "";
  if (!ctx.recent_messages.length) {
    feed.innerHTML = `<div class="empty-state">No messages logged yet. Set your Chat Style & Target above and test a message below!</div>`;
  } else {
    ctx.recent_messages.forEach((m) => {
      const row = document.createElement("div");
      row.className = `msg-row ${m.sender === "me" ? "me" : "her"}`;
      row.innerHTML = `
        <div class="bubble"></div>
        <div class="msg-meta">${m.sender === "me" ? "You (PulseAI)" : c.name} • ${m.timestamp || ""}</div>
      `;
      row.querySelector(".bubble").textContent = m.content;
      feed.appendChild(row);
    });
    feed.scrollTop = feed.scrollHeight;
  }

  // Co-pilot chips
  const cp = ctx.copilot;
  if (cp) {
    $("copilotBar").classList.remove("hidden");
    const box = $("copilotChips");
    box.innerHTML = "";
    [
      { label: cp.opt1_label || "Option 1", bubbles: cp.opt1 || [] },
      { label: cp.opt2_label || "Option 2", bubbles: cp.opt2 || [] },
      { label: cp.opt3_label || "Option 3", bubbles: cp.opt3 || [] },
    ].forEach((opt) => {
      if (!opt.bubbles.length) return;
      const btn = document.createElement("button");
      btn.className = "chip-btn";
      btn.textContent = `${opt.label}: ${opt.bubbles.join(" | ")}`;
      btn.onclick = async () => {
        await api(`/api/contacts/${cid}/send`, {
          method: "POST",
          body: JSON.stringify({ bubbles: opt.bubbles }),
        });
        showToast(`Sent ${opt.label} reply!`);
        await loadContactDetail(cid);
      };
      box.appendChild(btn);
    });
  } else {
    $("copilotBar").classList.add("hidden");
  }

  // Right Intel Panel
  $("intelName").textContent = c.name || c.handle;
  $("intelHandle").textContent = c.platform === "instagram" ? `@${c.handle}` : c.handle;
  $("intelBio").textContent = p.bio_summary || "No bio scanned yet.";
  $("intelRole").textContent = p.role_company || "—";

  const isLI = c.platform === "linkedin";
  $("secRole").classList.toggle("hidden", !isLI);
  $("secSkills").classList.toggle("hidden", !isLI);
  $("secActivity").classList.toggle("hidden", !isLI);
  $("secSongs").classList.toggle("hidden", isLI);
  $("secHobbies").classList.toggle("hidden", isLI);
  $("secLikes").classList.toggle("hidden", isLI);

  renderTags("intelSongs", p.fav_songs, true);
  renderTags("intelHobbies", p.hobbies);
  renderTags("intelLikes", p.likes);
  renderTags("intelSkills", p.skills, true);
  renderTags("intelActivity", p.recent_activity);

  const factsEl = $("intelFacts");
  factsEl.innerHTML = "";
  if (!ctx.memory_facts.length) {
    factsEl.innerHTML = `<span class="muted-label">Auto-learns from chats</span>`;
  } else {
    ctx.memory_facts.forEach((f) => {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.innerHTML = `<span>${f.fact}</span><span class="del-x" title="Remove">×</span>`;
      tag.querySelector(".del-x").onclick = async () => {
        await api(`/api/facts/${f.id}`, { method: "DELETE" });
        await loadContactDetail(cid);
      };
      factsEl.appendChild(tag);
    });
  }

  $("stageSelect").value = c.stage || "casual";
  const score = Number(c.warmth_score || 4);
  $("warmthLabel").textContent = `${score}/10`;
  const meter = $("warmthMeter");
  meter.innerHTML = "";
  for (let i = 1; i <= 10; i++) {
    const seg = document.createElement("div");
    seg.className = `warmth-seg ${i <= score ? "filled" : ""}`;
    seg.style.cursor = "pointer";
    seg.title = `Set warmth to ${i}/10`;
    seg.onclick = async () => {
      await api(`/api/contacts/${cid}`, { method: "PUT", body: JSON.stringify({ warmth_score: i }) });
      await loadContactDetail(cid);
    };
    meter.appendChild(seg);
  }
}

async function pollState() {
  try {
    const st = await api("/api/state");
    lastState = st;

    document.querySelectorAll("#modePills .pill").forEach((p) => {
      p.classList.toggle("active", p.dataset.mode === st.mode);
    });

    const gBadge = $("geminiBadge");
    gBadge.classList.toggle("online", st.gemini_connected);
    $("geminiStatusText").textContent = st.gemini_connected
      ? `Gemini AI: ${st.primary_model}`
      : "Gemini AI: Add API Key in Settings";

    if (st.platforms[currentView]) {
      const ps = st.platforms[currentView];
      $("antiBanStatus").textContent =
        `Status: ${ps.status} | Poll: ${ps.poll} | Speed: ${ps.type_speed} | Hourly Cap: ${ps.used}/${ps.max}`;
    }

    if (st.pending_approvals && st.pending_approvals.length > 0) {
      const first = st.pending_approvals[0];
      if (currentApprovalId !== first.id) {
        currentApprovalId = first.id;
        $("approvalReason").textContent = `${first.contact_name} (${first.platform}) — ${first.reason}`;
        $("approvalEditBox").value = first.bubbles.join("\n");
      }
      $("approvalBanner").classList.remove("hidden");
    } else {
      currentApprovalId = null;
      $("approvalBanner").classList.add("hidden");
    }

    if (currentView === "database") {
      renderLogs(st.logs);
    }
  } catch (e) {
    // quiet retry
  }
}

function renderLogs(logs) {
  const box = $("activityLogs");
  box.innerHTML = "";
  (logs || []).forEach((l) => {
    const div = document.createElement("div");
    div.className = `log-line ${l.level || "info"}`;
    div.textContent = `[${l.timestamp}] [${l.platform.toUpperCase()}] ${l.message}`;
    box.appendChild(div);
  });
  box.scrollTop = box.scrollHeight;
}

async function loadDatabaseView() {
  const data = await api("/api/contacts");
  const tbody = $("dbContactsTable").querySelector("tbody");
  tbody.innerHTML = "";
  data.contacts.forEach((c) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${c.platform}</td>
      <td>${c.name}</td>
      <td>${c.handle}</td>
      <td>${c.chat_target || "—"}</td>
      <td>${c.stage}</td>
      <td>${c.warmth_score}/10</td>
      <td><button class="btn-ghost btn-xs del-btn">Delete</button></td>
    `;
    tr.querySelector(".del-btn").onclick = async () => {
      await api(`/api/contacts/${c.id}`, { method: "DELETE" });
      showToast("Contact removed.");
      await loadDatabaseView();
    };
    tbody.appendChild(tr);
  });
  if (lastState) renderLogs(lastState.logs);
}

async function loadSettingsView() {
  const cfg = await api("/api/config");
  $("cfgApiKey").value = cfg.gemini_api_key || "";
  $("cfgPrimaryModel").value = cfg.primary_model || "gemini-3.5-flash";
  $("cfgProposeModel").value = cfg.propose_model || "gemini-3.5-flash";
  $("cfgFallbackModel").value = cfg.fallback_model || "gemini-3.5-flash";
  $("cfgBaseUrl").value = cfg.custom_base_url || "";
  $("cfgYourName").value = cfg.your_name || "";

  $("igPollMin").value = cfg.delays.instagram.poll_min_sec;
  $("igPollMax").value = cfg.delays.instagram.poll_max_sec;
  $("igCap").value = cfg.delays.instagram.max_replies_per_hour;

  $("waPollMin").value = cfg.delays.whatsapp.poll_min_sec;
  $("waPollMax").value = cfg.delays.whatsapp.poll_max_sec;
  $("waCap").value = cfg.delays.whatsapp.max_replies_per_hour;

  $("liPollMin").value = cfg.delays.linkedin.poll_min_sec;
  $("liPollMax").value = cfg.delays.linkedin.poll_max_sec;
  $("liCap").value = cfg.delays.linkedin.max_replies_per_hour;
}

// EVENT LISTENERS
document.querySelectorAll(".nav-item").forEach((el) => {
  el.onclick = () => switchView(el.dataset.view);
});

document.querySelectorAll("#modePills .pill").forEach((el) => {
  el.onclick = async () => {
    await api("/api/mode", { method: "POST", body: JSON.stringify({ mode: el.dataset.mode }) });
    showToast(`Switched to ${el.dataset.mode.toUpperCase()} mode`);
    await pollState();
  };
});

$("btnStart").onclick = async () => {
  showToast("Launching Chrome browser tabs (WhatsApp, Insta, LinkedIn)...");
  try {
    await api("/api/engine/start", { method: "POST" });
    showToast("Engine started! Log into tabs once if needed.");
    await pollState();
  } catch (e) {
    showToast(`Start error: ${e.message}`);
  }
};

$("btnPause").onclick = async () => {
  await api("/api/engine/pause", { method: "POST" });
  showToast("Engine paused.");
  await pollState();
};

$("contactSelector").onchange = async (e) => {
  currentContactId = Number(e.target.value);
  await loadContactDetail(currentContactId);
};

$("btnSaveStrategy").onclick = saveStrategy;
$("chatStyleInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") saveStrategy();
});
$("chatTargetInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") saveStrategy();
});

document.querySelectorAll(".persona-pill").forEach((btn) => {
  btn.onclick = async () => {
    if (!currentContactId) return;
    await api(`/api/contacts/${currentContactId}`, {
      method: "PUT",
      body: JSON.stringify({ persona: btn.dataset.persona }),
    });
    showToast(`Persona set to ${btn.dataset.persona}`);
    await loadContactDetail(currentContactId);
  };
});

$("stageSelect").onchange = async (e) => {
  if (!currentContactId) return;
  await api(`/api/contacts/${currentContactId}`, {
    method: "PUT",
    body: JSON.stringify({ stage: e.target.value }),
  });
  showToast(`Stage updated to ${e.target.value}`);
};

async function handleSend() {
  if (!currentContactId) return showToast("Select a contact first.");
  const input = $("chatInput");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";

  const dir = $("inputDirection").value;
  try {
    if (dir === "simulate") {
      showToast("Gemini thinking with your Style & Target...");
      await api(`/api/contacts/${currentContactId}/simulate`, {
        method: "POST",
        body: JSON.stringify({ text }),
      });
    } else {
      await api(`/api/contacts/${currentContactId}/send`, {
        method: "POST",
        body: JSON.stringify({ text }),
      });
    }
    await loadContactDetail(currentContactId);
    await pollState();
  } catch (e) {
    showToast(`Error: ${e.message}`);
  }
}

$("btnSendMsg").onclick = handleSend;
$("chatInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") handleSend();
});

$("btnPropose").onclick = async () => {
  if (!currentContactId) return showToast("Select a contact first.");
  const typedTarget = $("chatTargetInput").value.trim();
  showToast(`Executing target: ${typedTarget || "Propose"}...`);
  try {
    await api(`/api/contacts/${currentContactId}/propose`, {
      method: "POST",
      body: JSON.stringify({ target_override: typedTarget }),
    });
    await loadContactDetail(currentContactId);
    await pollState();
  } catch (e) {
    showToast(`Error: ${e.message}`);
  }
};

$("btnScanProfile").onclick = async () => {
  if (!currentContactId) return;
  showToast("Scanning profile & songs slowly in Chrome... please wait 15-25s.");
  try {
    await api(`/api/contacts/${currentContactId}/scan`, { method: "POST" });
    showToast("Profile Intel & Songs saved to SQLite!");
    await loadContactDetail(currentContactId);
  } catch (e) {
    showToast(`Scan error: ${e.message}`);
  }
};

$("btnAddFact").onclick = async () => {
  if (!currentContactId) return;
  const val = $("newFactInput").value.trim();
  if (!val) return;
  $("newFactInput").value = "";
  await api(`/api/contacts/${currentContactId}/facts`, {
    method: "POST",
    body: JSON.stringify({ category: "inside_joke", fact: val }),
  });
  await loadContactDetail(currentContactId);
};

$("btnApproveSend").onclick = async () => {
  if (!currentApprovalId) return;
  const bubbles = $("approvalEditBox").value.split("\n").map((s) => s.trim()).filter(Boolean);
  await api(`/api/approvals/${currentApprovalId}`, {
    method: "POST",
    body: JSON.stringify({ action: "approve", bubbles }),
  });
  showToast("Approved & sent!");
  await pollState();
  if (currentContactId) await loadContactDetail(currentContactId);
};

$("btnRejectSend").onclick = async () => {
  if (!currentApprovalId) return;
  await api(`/api/approvals/${currentApprovalId}`, {
    method: "POST",
    body: JSON.stringify({ action: "reject" }),
  });
  showToast("Skipped.");
  await pollState();
};

// Modal Add Contact
$("btnQuickAdd").onclick = () => {
  $("newContactPlatform").value = currentView;
  $("newContactPersona").value = currentView === "linkedin" ? "professional" : "personal";
  $("addModal").classList.remove("hidden");
};
$("btnCancelModal").onclick = () => $("addModal").classList.add("hidden");
$("btnConfirmAdd").onclick = async () => {
  const payload = {
    platform: $("newContactPlatform").value,
    name: $("newContactName").value.trim(),
    handle: $("newContactHandle").value.trim(),
    profile_url: $("newContactUrl").value.trim(),
    persona: $("newContactPersona").value,
    chat_style: $("newContactStyle").value.trim(),
    chat_target: $("newContactTarget").value.trim(),
  };
  if (!payload.handle) return showToast("Handle / Contact name is required.");
  await api("/api/contacts", { method: "POST", body: JSON.stringify(payload) });
  $("addModal").classList.add("hidden");
  $("newContactName").value = "";
  $("newContactHandle").value = "";
  $("newContactUrl").value = "";
  $("newContactStyle").value = "";
  $("newContactTarget").value = "";
  showToast("Added to whitelist!");
  await loadContactsForPlatform(currentView);
};

// Settings Save
$("btnSaveSettings").onclick = async () => {
  const payload = {
    gemini_api_key: $("cfgApiKey").value.trim(),
    primary_model: $("cfgPrimaryModel").value.trim(),
    propose_model: $("cfgProposeModel").value.trim(),
    fallback_model: $("cfgFallbackModel").value.trim(),
    custom_base_url: $("cfgBaseUrl").value.trim(),
    your_name: $("cfgYourName").value.trim(),
    delays: {
      instagram: {
        poll_min_sec: Number($("igPollMin").value),
        poll_max_sec: Number($("igPollMax").value),
        max_replies_per_hour: Number($("igCap").value),
      },
      whatsapp: {
        poll_min_sec: Number($("waPollMin").value),
        poll_max_sec: Number($("waPollMax").value),
        max_replies_per_hour: Number($("waCap").value),
      },
      linkedin: {
        poll_min_sec: Number($("liPollMin").value),
        poll_max_sec: Number($("liPollMax").value),
        max_replies_per_hour: Number($("liCap").value),
      },
    },
  };
  const res = await api("/api/config", { method: "POST", body: JSON.stringify(payload) });
  showToast(res.gemini_connected ? "Settings saved & Gemini Connected!" : "Settings saved (check API key).");
  await pollState();
};

$("btnExportDb").onclick = async () => {
  const data = await api("/api/export");
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "pulseai_memory_export.json";
  a.click();
};

// INIT
switchView("instagram");
pollState();
setInterval(pollState, 3000);
