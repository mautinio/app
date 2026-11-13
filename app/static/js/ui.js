/** Общие UI-утилиты: экранирование, форматирование, уведомления, автокомплит. */

export const $ = (selector, root = document) => root.querySelector(selector);

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ESCAPES[c]);

export const fmt = (n, digits = 0) =>
  Number(n || 0).toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits });

/** Даты от бэкенда без зоны — это UTC. */
export const fmtDate = (iso) => new Date(/[Z+]/.test(iso.slice(-6)) ? iso : `${iso}Z`).toLocaleString("ru-RU");

/** «[123] название» или «123» в поле ввода -> 123. */
export const parseId = (input) => Number(input.dataset.id || (input.value.trim().match(/^\[?(\d+)\]?$/) || [])[1]) || null;

export const offerLabel = (o) => `<span class="id">[${o.id}]</span>${esc(o.name)}`;

class Toast {
  #el = $("#toast");
  #timer;

  show(message, isError = false) {
    this.#el.textContent = message;
    this.#el.className = isError ? "error" : "";
    this.#el.hidden = false;
    clearTimeout(this.#timer);
    this.#timer = setTimeout(() => (this.#el.hidden = true), isError ? 6000 : 3000);
  }

  error = (message) => this.show(message, true);
}

export const toast = new Toast();

/**
 * Автокомплит поверх <input> с соседним <ul class="ac-list">.
 * search(query) -> Promise<items>, render(item) -> html, onSelect(item).
 */
export class Autocomplete {
  static DEBOUNCE_MS = 200;
  #input; #list; #search; #render; #onSelect;
  #items = []; #highlighted = -1; #timer; #requestSeq = 0;

  constructor(input, { search, render, onSelect }) {
    this.#input = input;
    this.#list = input.parentElement.querySelector(".ac-list");
    this.#search = search;
    this.#render = render;
    this.#onSelect = onSelect;
    this.#bind();
  }

  #bind() {
    this.#input.addEventListener("input", () => {
      this.#input.dataset.id = "";
      clearTimeout(this.#timer);
      this.#timer = setTimeout(() => this.#load(), Autocomplete.DEBOUNCE_MS);
    });
    this.#input.addEventListener("focus", () => this.#load());
    this.#input.addEventListener("blur", () => setTimeout(() => this.#close(), 150));
    this.#input.addEventListener("keydown", (e) => this.#onKey(e));
    this.#list.addEventListener("mousedown", (e) => {
      const li = e.target.closest("li[data-i]");
      if (li) { e.preventDefault(); this.#pick(Number(li.dataset.i)); }
    });
  }

  #onKey(e) {
    if (this.#list.hidden) return;
    const moves = { ArrowDown: 1, ArrowUp: -1 };
    if (e.key in moves) {
      this.#highlighted = Math.max(0, Math.min(this.#highlighted + moves[e.key], this.#items.length - 1));
      this.#draw();
    } else if (e.key === "Enter" && this.#highlighted >= 0) {
      this.#pick(this.#highlighted);
    } else if (e.key === "Escape") {
      this.#close();
      return;
    } else {
      return;
    }
    e.preventDefault();
  }

  async #load() {
    const seq = ++this.#requestSeq; // ответы на устаревшие запросы игнорируем
    try {
      const items = await this.#search(this.#input.value.trim());
      if (seq !== this.#requestSeq) return;
      this.#items = items;
      this.#highlighted = items.length ? 0 : -1;
      this.#draw();
    } catch (e) {
      toast.error(e.message);
    }
  }

  #draw() {
    this.#list.innerHTML = this.#items.length
      ? this.#items.map((it, i) => `<li data-i="${i}" class="${i === this.#highlighted ? "hl" : ""}">${this.#render(it)}</li>`).join("")
      : `<li class="empty">Ничего не найдено</li>`;
    this.#list.hidden = false;
  }

  #pick(index) {
    const item = this.#items[index];
    if (!item) return;
    this.#close();
    this.#onSelect(item);
  }

  #close() {
    this.#list.hidden = true;
    this.#highlighted = -1;
  }
}

/** Автокомплит выбора оффера: в поле пишет «[id] name» и запоминает id. */
export function offerPicker(input, search) {
  return new Autocomplete(input, {
    search,
    render: offerLabel,
    onSelect: (o) => { input.value = `[${o.id}] ${o.name}`; input.dataset.id = o.id; },
  });
}
