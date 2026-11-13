import { api } from "./api.js";
import { $, Autocomplete, esc, fmtDate, toast } from "./ui.js";
import { StreamCard } from "./stream-card.js";

const HISTORY_LABELS = { push: "опубликовано в Keitaro", cancel: "черновик отменён" };

/** Вкладка «Редактор офферов»: выбор кампании, Fetch из Keitaro, потоки и история. */
export class EditorView {
  #campaignId = null;
  #adminUrl = null;
  #onCampaignsChanged;
  #onOpened;
  #select = $("#campaign-select");
  #fetchButton = $("#fetch-btn");
  #container = $("#editor");

  constructor({ onCampaignsChanged, onOpened }) {
    this.#onCampaignsChanged = onCampaignsChanged;
    this.#onOpened = onOpened;
    const today = new Date().toISOString().slice(0, 10);
    $("#date-from").value = today;
    $("#date-to").value = today;
    this.#bind();
  }

  get campaignId() { return this.#campaignId; }

  setAdminUrl(url) { this.#adminUrl = url; }

  renderCampaignList(campaigns) {
    this.#select.innerHTML = `<option value="">— выберите кампанию —</option>` +
      campaigns.map((c) => `<option value="${c.id}">#${c.id} ${esc(c.name)}</option>`).join("");
    this.#select.value = this.#campaignId ? String(this.#campaignId) : "";
  }

  async open(campaignId) {
    this.#container.classList.add("loading");
    try {
      const period = { from: $("#date-from").value, to: $("#date-to").value };
      const [campaign, history] = await Promise.all([api.campaign(campaignId, period), api.history(campaignId)]);
      this.#campaignId = campaignId;
      this.#select.value = String(campaignId);
      this.#fetchButton.disabled = false;
      this.#updateKeitaroLink();
      this.#render(campaign, history);
      this.#onOpened(campaignId);
    } catch (e) {
      toast.error(e.message);
    } finally {
      this.#container.classList.remove("loading");
    }
  }

  #bind() {
    this.#select.addEventListener("change", (e) => e.target.value && this.open(Number(e.target.value)));
    const search = $("#kt-search");
    new Autocomplete(search, {
      search: (q) => api.searchKeitaroCampaigns(q),
      render: (c) => `<span class="id">#${c.id}</span>${esc(c.name)} <span class="muted">/${esc(c.alias)}</span>`,
      onSelect: (c) => { search.value = ""; this.#fetch(c.id); },
    });
    this.#fetchButton.addEventListener("click", () => this.#confirmAndFetch());
    const reload = () => this.#campaignId && this.open(this.#campaignId);
    $("#refresh").addEventListener("click", reload);
    $("#date-from").addEventListener("change", reload);
    $("#date-to").addEventListener("change", reload);
  }

  #confirmAndFetch() {
    if (!this.#campaignId) return;
    const hasDrafts = this.#container.querySelector(".stream.dirty");
    if (hasDrafts && !confirm("В кампании есть неопубликованные изменения. Fetch заменит их тем, что сейчас в Keitaro. Продолжить?")) return;
    this.#fetch(this.#campaignId);
  }

  async #fetch(campaignId) {
    this.#fetchButton.disabled = true;
    try {
      await api.fetchCampaign(campaignId);
      toast.show("Потоки загружены из Keitaro");
      this.#campaignId = campaignId;
      await this.#onCampaignsChanged();
      await this.open(campaignId);
    } catch (e) {
      toast.error(e.message);
    } finally {
      this.#fetchButton.disabled = !this.#campaignId;
    }
  }

  #updateKeitaroLink() {
    const link = $("#view-kt");
    link.hidden = !this.#adminUrl;
    if (this.#adminUrl) link.href = `${this.#adminUrl}#!/campaigns/${this.#campaignId}`;
  }

  #render(c, history) {
    const cards = c.streams.map((s) => new StreamCard(s, { onChanged: () => this.open(this.#campaignId) }));
    this.#container.innerHTML = `
      <div class="card"><h2 style="margin:0">#${c.id} ${esc(c.name)}
        <span class="muted" style="font-size:14px;font-weight:400">/${esc(c.alias)} · ${esc(c.state)} ·
        загружено из Keitaro: ${c.fetched_at ? fmtDate(c.fetched_at) : "—"}</span></h2>
        ${c.url ? `<div style="margin-top:6px"><a href="${esc(c.url)}" target="_blank">${esc(c.url)}</a></div>` : ""}
        ${c.stats_error ? `<div class="err" style="margin-top:8px">Статистика недоступна: ${esc(c.stats_error)}</div>` : ""}
      </div>
      ${cards.map((card) => card.html()).join("") || '<div class="card muted">В кампании нет потоков</div>'}
      <div class="card"><h3>История публикаций</h3>${EditorView.#historyHtml(history)}</div>`;
    cards.forEach((card) => card.mount(this.#container));
  }

  static #historyHtml(history) {
    if (!history.length) return `<span class="muted">Публикаций ещё не было</span>`;
    const offers = (after) => after.filter((o) => o.status === "active")
      .map((o) => `${o.offer_id}: ${o.share}%${o.pinned ? " 📌" : ""}`).join(", ") || "нет активных офферов";
    return `<ul class="history">${history.map((h) => `<li><span class="muted">${fmtDate(h.created_at)}</span>
      поток #${h.stream_id}: ${HISTORY_LABELS[h.action] || h.action} → ${offers(h.after)}</li>`).join("")}</ul>`;
  }
}
