import { api } from "./api.js";
import { $, esc, offerPicker, parseId } from "./ui.js";

/** Вкладка «Создать кампанию»: форма создатора и список созданных кампаний. */
export class CreatorView {
  #form = $("#create-form");
  #offerInput = $("#create-offer");
  #result = $("#create-result");
  #onCreated;

  constructor({ onCreated }) {
    this.#onCreated = onCreated;
    offerPicker(this.#offerInput, (q) => api.searchOffers(q));
    this.#form.addEventListener("submit", (e) => { e.preventDefault(); this.#submit(); });
  }

  fillReferences(meta) {
    const { domain_id, group_id, traffic_source_id } = meta.defaults;
    CreatorView.#fillSelect(this.#form.domain_id, meta.domains, domain_id);
    CreatorView.#fillSelect(this.#form.group_id, meta.groups, group_id);
    CreatorView.#fillSelect(this.#form.traffic_source_id, meta.traffic_sources, traffic_source_id);
  }

  renderCreated(campaigns) {
    const rows = campaigns.filter((c) => c.created_by_wrapper);
    $("#created-table tbody").innerHTML = rows.length
      ? rows.map((c) => `<tr>
          <td>${c.id}</td><td>${esc(c.name)}</td><td>${esc((c.geo || []).join(", "))}</td>
          <td>${c.url ? `<a href="${esc(c.url)}" target="_blank">${esc(c.url)}</a>` : "—"}</td>
          <td><button class="link" data-open="${c.id}">редактор</button></td></tr>`).join("")
      : `<tr><td colspan="5" class="muted">Пока ничего не создано</td></tr>`;
  }

  static #fillSelect(select, items, preferred) {
    const selected = preferred ?? items[0]?.id;
    select.innerHTML = `<option value="">— не выбрано —</option>` +
      items.map((i) => `<option value="${i.id}" ${i.id === selected ? "selected" : ""}>${esc(i.name)} (#${i.id})</option>`).join("");
  }

  async #submit() {
    const offerId = parseId(this.#offerInput);
    if (!offerId) return this.#showResult("Выберите оффер из списка", true);
    const form = this.#form;
    const optional = (v) => (v ? Number(v) : null);
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    button.textContent = "Создаём…";
    try {
      const c = await api.createCampaign({
        name: form.name.value,
        geo: form.geo.value,
        offer_id: offerId,
        domain_id: optional(form.domain_id.value),
        group_id: optional(form.group_id.value),
        traffic_source_id: optional(form.traffic_source_id.value),
      });
      this.#showResult(`Кампания <b>#${c.id} ${esc(c.name)}</b> создана.<br>
        Поток 1: ${esc(c.geo.join(", "))} → Google, поток 2: оффер #${offerId}.<br>
        ${c.url ? `URL: <a href="${esc(c.url)}" target="_blank">${esc(c.url)}</a><br>` : ""}
        <button class="link" data-open="${c.id}">Открыть в редакторе →</button>`);
      form.reset();
      this.#offerInput.dataset.id = "";
      this.#onCreated(c);
    } catch (e) {
      this.#showResult(esc(e.message), true);
    } finally {
      button.disabled = false;
      button.textContent = "Create";
    }
  }

  /** html должен быть уже экранирован. */
  #showResult(html, isError = false) {
    this.#result.innerHTML = `<div class="result ${isError ? "error" : ""}">${html}</div>`;
  }
}
