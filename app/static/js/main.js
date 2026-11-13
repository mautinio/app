import { api } from "./api.js";
import { $, toast } from "./ui.js";
import { CreatorView } from "./creator.js";
import { EditorView } from "./editor.js";

/** Корень приложения: вкладки, адрес в URL (#create, #edit/<id>), связь между вкладками. */
class App {
  #creator = new CreatorView({ onCreated: () => this.#reloadCampaigns() });
  #editor = new EditorView({
    onCampaignsChanged: () => this.#reloadCampaigns(),
    onOpened: () => this.#syncHash(),
  });
  #tab = "create";

  async start() {
    document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => this.showTab(b.dataset.tab)));
    document.addEventListener("click", (e) => {
      const link = e.target.closest("[data-open]");
      if (link) this.openInEditor(Number(link.dataset.open));
    });
    this.#restoreFromHash();
    await Promise.all([this.#loadMeta(), this.#reloadCampaigns()]);
  }

  showTab(name) {
    this.#tab = name;
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
    $("#tab-create").hidden = name !== "create";
    $("#tab-edit").hidden = name !== "edit";
    this.#syncHash();
  }

  openInEditor(campaignId) {
    this.showTab("edit");
    this.#editor.open(campaignId);
  }

  async #loadMeta() {
    try {
      const meta = await api.meta();
      $("#mock-badge").hidden = !meta.mock;
      this.#editor.setAdminUrl(meta.keitaro_admin_url);
      this.#creator.fillReferences(meta);
    } catch (e) {
      toast.error(`Не удалось загрузить справочники Keitaro: ${e.message}`);
    }
  }

  async #reloadCampaigns() {
    try {
      const campaigns = await api.campaigns();
      this.#creator.renderCreated(campaigns);
      this.#editor.renderCampaignList(campaigns);
    } catch (e) {
      toast.error(e.message);
    }
  }

  #syncHash() {
    const id = this.#editor.campaignId;
    const hash = this.#tab === "edit" && id ? `#edit/${id}` : `#${this.#tab}`;
    if (location.hash !== hash) history.replaceState(null, "", hash);
  }

  #restoreFromHash() {
    const match = location.hash.match(/^#edit(?:\/(\d+))?/);
    if (!match) return;
    if (match[1]) this.openInEditor(Number(match[1]));
    else this.showTab("edit");
  }
}

new App().start();
