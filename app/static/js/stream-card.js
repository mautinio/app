import { api } from "./api.js";
import { esc, fmt, offerPicker, parseId, toast } from "./ui.js";

const METRIC_COLUMNS = `<th class="num">Клики</th><th class="num">Уник.</th><th class="num">Боты</th>
  <th class="num">Конв.</th><th class="num">CR</th><th class="num">Доход</th>`;

function metricCells(m = {}) {
  const cr = m.clicks ? (m.conversions / m.clicks) * 100 : 0;
  return `<td class="num">${fmt(m.clicks)}</td><td class="num">${fmt(m.stream_unique_clicks)}</td>
    <td class="num">${fmt(m.bots)}</td><td class="num">${fmt(m.conversions)}</td>
    <td class="num">${fmt(cr, 2)}%</td><td class="num">${fmt(m.revenue, 2)}</td>`;
}

function sumMetrics(rows) {
  const total = {};
  for (const { stats = {} } of rows) for (const [k, v] of Object.entries(stats)) total[k] = (total[k] || 0) + v;
  return total;
}

/** Подпись под долей: чем черновик отличается от Keitaro. */
function draftHint(o) {
  if (!o.dirty) return "";
  if (o.published) return `в KT: ${o.pushed_share}%`;
  return o.pushed_status === "removed" ? "возвращён" : "новый";
}

/** Карточка одного потока: рендер + обработчики. После любого изменения просит редактор перерисоваться. */
export class StreamCard {
  #stream;
  #onChanged;
  #root;

  constructor(stream, { onChanged }) {
    this.#stream = stream;
    this.#onChanged = onChanged;
  }

  html() {
    const s = this.#stream;
    const st = s.stats || {};
    const head = `<div class="stream-head">
        <span class="title">Stream: ${esc(s.name)}</span>
        <span class="muted">#${s.position} · stream_id ${s.id}</span>
        <div class="stats">
          <div><b>${fmt(st.clicks)}</b><span>Клики</span></div>
          <div><b>${fmt(st.stream_unique_clicks)}</b><span>Уник.</span></div>
          <div><b>${fmt(st.bots)}</b><span>Боты</span></div>
        </div>
      </div>`;
    if (!s.has_offers) {
      return `<div class="card stream">${head}<div class="stream-body muted">Поток без офферов</div></div>`;
    }
    const draftBar = s.dirty
      ? `<div class="draft-bar"><button class="push">⬆ Push to KT</button><button class="cancel">✕ Cancel</button>
         <span class="muted">Есть неопубликованные изменения — в Keitaro их пока нет</span></div>`
      : "";
    return `<div class="card stream ${s.dirty ? "dirty" : ""}" data-stream="${s.id}">${head}${draftBar}
      <div class="stream-body">${this.#table()}${this.#addForm()}</div></div>`;
  }

  /** Вызывается после вставки html() в DOM. */
  mount(container) {
    if (!this.#stream.has_offers) return;
    this.#root = container.querySelector(`[data-stream="${this.#stream.id}"]`);
    this.#bindStreamActions();
    this.#root.querySelectorAll("tr[data-offer]").forEach((tr) => this.#bindOfferRow(tr));
  }

  #table() {
    const s = this.#stream;
    const rows = s.offers.map((o) => this.#offerRow(o)).join("") + s.untracked_offers.map((o) => `
      <tr class="removed" title="Оффер получал клики в этом потоке, но убран из него ещё до загрузки кампании в обёртку">
        <td>[${o.offer_id}] <i>(не в обёртке)</i></td><td class="num">—</td>${metricCells(o.stats)}<td></td></tr>`).join("");
    const total = sumMetrics([...s.offers, ...s.untracked_offers]);
    return `<table class="grid">
      <thead><tr><th>Оффер</th><th class="num">Доля</th>${METRIC_COLUMNS}<th class="num">Действия</th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr class="total-row"><td>Итого</td>
        <td class="num ${s.shares_total === 100 ? "ok" : "err"}">${s.shares_total}%</td>${metricCells(total)}<td></td></tr></tfoot>
    </table>`;
  }

  #offerRow(o) {
    const removed = o.status !== "active";
    const hint = draftHint(o);
    return `<tr data-offer="${o.offer_id}" class="${removed ? "removed" : ""} ${o.dirty ? "changed" : ""}">
      <td class="offer-name">[${o.offer_id}] ${esc(o.name) || "—"}${removed ? " <i>(removed)</i>" : ""}</td>
      <td class="num share-cell">
        <button class="share-link" ${removed ? "disabled" : ""} title="Задать долю вручную (оффер закрепится)">${o.share}%</button>
        <button class="pin ${o.pinned ? "on" : ""}" ${removed ? "disabled" : ""}
          title="${o.pinned ? "Открепить" : "Закрепить долю: при пересчётах она не меняется"}">📌</button>
        ${hint ? `<div class="was">${hint}</div>` : ""}
      </td>
      ${metricCells(o.stats)}
      <td class="num">${removed ? `<button class="bring-back">↺ Bring back</button>` : `<button class="remove">🗑 Remove</button>`}</td>
    </tr>`;
  }

  #addForm() {
    return `<div class="actions">
      <div class="ac"><input class="add-offer" placeholder="Добавить оффер: ID или название"><ul class="ac-list" hidden></ul></div>
      <button class="primary add-btn">Add</button>
    </div>`;
  }

  /** Выполнить действие над потоком и перерисовать редактор; при ошибке — показать её. */
  async #run(action, successMessage) {
    this.#root.classList.add("loading");
    try {
      await action();
      if (successMessage) toast.show(successMessage);
      await this.#onChanged();
    } catch (e) {
      toast.error(e.message);
      this.#root.classList.remove("loading");
    }
  }

  #bindStreamActions() {
    const id = this.#stream.id;
    const activeIds = new Set(this.#stream.offers.filter((o) => o.status === "active").map((o) => o.offer_id));
    const input = this.#root.querySelector(".add-offer");
    offerPicker(input, async (q) => (await api.searchOffers(q)).filter((o) => !activeIds.has(o.id)));

    this.#root.querySelector(".add-btn").addEventListener("click", () => {
      const offerId = parseId(input);
      if (!offerId) return toast.error("Выберите оффер из списка");
      this.#run(() => api.addOffer(id, offerId), `Оффер #${offerId} добавлен в черновик`);
    });
    this.#root.querySelector(".push")?.addEventListener("click", () => this.#run(() => api.push(id), "Опубликовано в Keitaro"));
    this.#root.querySelector(".cancel")?.addEventListener("click", () => this.#run(() => api.cancel(id), "Изменения отменены"));
  }

  #bindOfferRow(tr) {
    const streamId = this.#stream.id;
    const offer = this.#stream.offers.find((o) => o.offer_id === Number(tr.dataset.offer));
    const on = (selector, handler) => tr.querySelector(selector)?.addEventListener("click", handler);
    on(".remove", () => this.#run(() => api.removeOffer(streamId, offer.offer_id)));
    on(".bring-back", () => this.#run(() => api.bringBack(streamId, offer.offer_id)));
    on(".pin", () => this.#run(() => api.pin(streamId, offer.offer_id, !offer.pinned)));
    on(".share-link", (e) => this.#editShare(e.target.closest("td"), offer));
  }

  /** Клик по доле -> поле ввода; Enter/blur сохраняет (оффер закрепляется), Esc отменяет. */
  #editShare(cell, offer) {
    cell.innerHTML = `<input class="share-input" type="number" min="0" max="100" value="${offer.share}"> %`;
    const input = cell.querySelector("input");
    input.focus();
    input.select();
    let finished = false;
    const finish = (save) => {
      if (finished) return;
      finished = true;
      const value = Number(input.value);
      if (!save || input.value === "" || value === offer.share) return this.#onChanged();
      if (!Number.isInteger(value) || value < 0 || value > 100) {
        toast.error("Доля — целое число от 0 до 100");
        return this.#onChanged();
      }
      this.#run(() => api.setShare(this.#stream.id, offer.offer_id, value), `Доля закреплена: ${value}%`);
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") finish(true);
      if (e.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
  }
}
