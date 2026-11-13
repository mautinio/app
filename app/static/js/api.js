/** HTTP-клиент бэкенда: единственное место, которое знает URL и формат ошибок API. */
class ApiClient {
  async #request(method, url, body) {
    const response = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(ApiClient.#errorText(data, response));
    return data;
  }

  static #errorText(data, response) {
    const detail = data?.detail ?? response.statusText;
    // ошибки валидации FastAPI приходят списком
    return Array.isArray(detail) ? detail.map((e) => `${e.loc?.at(-1)}: ${e.msg}`).join("; ") : detail;
  }

  #get = (url) => this.#request("GET", url);
  #post = (url, body) => this.#request("POST", url, body);
  #q = (q) => encodeURIComponent(q);

  // справочники
  meta() { return this.#get("/api/meta"); }
  searchOffers(q) { return this.#get(`/api/offers?q=${this.#q(q)}`); }
  searchKeitaroCampaigns(q) { return this.#get(`/api/keitaro/campaigns?q=${this.#q(q)}`); }

  // кампании
  createCampaign(body) { return this.#post("/api/campaigns", body); }
  campaigns() { return this.#get("/api/campaigns"); }
  fetchCampaign(id) { return this.#post(`/api/campaigns/${id}/fetch`); }
  campaign(id, { from, to }) { return this.#get(`/api/campaigns/${id}?date_from=${from}&date_to=${to}`); }
  history(id) { return this.#get(`/api/campaigns/${id}/history`); }

  // редактор потока
  addOffer(streamId, offerId) { return this.#post(`/api/streams/${streamId}/offers`, { offer_id: offerId }); }
  removeOffer(streamId, offerId) { return this.#post(`/api/streams/${streamId}/offers/${offerId}/remove`); }
  bringBack(streamId, offerId) { return this.#post(`/api/streams/${streamId}/offers/${offerId}/bring-back`); }
  pin(streamId, offerId, pinned) { return this.#post(`/api/streams/${streamId}/offers/${offerId}/pin`, { pinned }); }
  setShare(streamId, offerId, share) { return this.#request("PUT", `/api/streams/${streamId}/offers/${offerId}/share`, { share }); }
  push(streamId) { return this.#post(`/api/streams/${streamId}/push`); }
  cancel(streamId) { return this.#post(`/api/streams/${streamId}/cancel`); }
}

export const api = new ApiClient();
