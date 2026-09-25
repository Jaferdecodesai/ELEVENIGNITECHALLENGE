const state = { currentCase: null };

const form = document.querySelector("#intake-form");
const approvalForm = document.querySelector("#approval-form");
const notice = document.querySelector("#notice");

function showNotice(message, isError = false) {
  notice.textContent = message;
  notice.classList.toggle("error", isError);
  notice.hidden = false;
  window.clearTimeout(showNotice.timeout);
  showNotice.timeout = window.setTimeout(() => { notice.hidden = true; }, 4500);
}

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({ error: "Invalid server response" }));
  if (!response.ok) throw new Error(payload.error || `Request failed with ${response.status}`);
  return payload;
}

function intakePayload() {
  const data = new FormData(form);
  return {
    clinic_id: data.get("clinic_id"),
    callback_number: data.get("callback_number"),
    synthetic_member_id: data.get("synthetic_member_id"),
    policy_id: data.get("policy_id"),
    procedure_code: data.get("procedure_code"),
    diagnosis_code: data.get("diagnosis_code"),
    cost_aed: Number(data.get("cost_aed")),
    urgency: data.get("urgency"),
    language: data.get("language"),
    documents: data.getAll("document"),
    disclosure_acknowledged: data.has("disclosure_acknowledged"),
    recording_consent: data.has("recording_consent"),
  };
}

function resetFlow() {
  document.querySelectorAll("#flow-list li").forEach((item) => item.classList.remove("done", "active"));
}

function showFlow(caseData) {
  resetFlow();
  const events = new Set(caseData.audit.map((item) => item.event));
  const done = ["disclosure", "intake"];
  if (!events.has("consent_required")) done.push("authentication");
  if (events.has("clinic_authenticated")) done.push("rules");
  if (events.has("rule_retrieved")) done.push("recommendation");
  if (caseData.human_decision) done.push("human");
  done.forEach((step) => document.querySelector(`[data-step="${step}"]`)?.classList.add("done"));
  if (!caseData.human_decision) document.querySelector('[data-step="human"]')?.classList.add("active");
}

function statusClass(status) {
  if (status === "approval_ready" || status === "human_approved") return "badge-success";
  if (status.includes("failed") || status.includes("denied")) return "badge-alert";
  if (status.includes("escalation") || status.includes("evidence")) return "badge-human";
  return "badge-info";
}

function renderCase(caseData) {
  state.currentCase = caseData;
  document.querySelector("#empty-result").hidden = true;
  document.querySelector("#case-result").hidden = false;
  document.querySelector("#case-id").textContent = caseData.case_id;
  document.querySelector("#recommendation").textContent = caseData.human_decision
    ? `Human ${caseData.human_decision}`
    : (caseData.recommendation || "No recommendation");
  document.querySelector("#rationale").textContent = caseData.human_reason || caseData.rationale;
  document.querySelector("#source").textContent = caseData.source || "No policy source used";
  const status = document.querySelector("#case-status");
  status.textContent = caseData.status.replaceAll("_", " ");
  status.className = `badge ${statusClass(caseData.status)}`;
  const events = document.querySelector("#audit-events");
  events.replaceChildren(...caseData.audit.map((event) => {
    const item = document.createElement("li");
    item.textContent = `${event.event.replaceAll("_", " ")} · ${event.actor}`;
    return item;
  }));
  showFlow(caseData);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const caseData = await request("/api/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(intakePayload()),
    });
    renderCase(caseData);
    showNotice("Synthetic case evaluated. No final outcome has been issued.");
  } catch (error) {
    showNotice(error.message, true);
  }
});

document.querySelector("#load-missing").addEventListener("click", () => {
  form.querySelectorAll('input[name="document"]').forEach((input) => { input.checked = false; });
  form.querySelector('input[name="document"][value="referral"]').checked = true;
  form.querySelector('[name="urgency"]').value = "routine";
  showNotice("Missing-evidence inputs loaded. Run the workflow.");
});

document.querySelector("#load-emergency").addEventListener("click", () => {
  form.querySelector('[name="urgency"]').value = "emergency";
  showNotice("Emergency escalation inputs loaded. Run the workflow.");
});

document.querySelectorAll(".decision").forEach((button) => {
  button.addEventListener("click", async () => {
    if (!state.currentCase) {
      showNotice("Run an intake case before recording a human decision.", true);
      return;
    }
    const data = new FormData(approvalForm);
    try {
      const caseData = await request(`/api/cases/${state.currentCase.case_id}/decision`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Approver-Token": data.get("token"),
        },
        body: JSON.stringify({
          decision: button.dataset.decision,
          reason: data.get("reason"),
          approver: data.get("approver"),
        }),
      });
      renderCase(caseData);
      showNotice(`Human decision recorded: ${button.dataset.decision}.`);
    } catch (error) {
      showNotice(error.message, true);
    }
  });
});

request("/api/health")
  .then(() => {
    const status = document.querySelector(".status-dot");
    status.classList.add("online");
    document.querySelector("#service-status").textContent = "Local service ready";
  })
  .catch(() => {
    document.querySelector("#service-status").textContent = "Service unavailable";
  });
