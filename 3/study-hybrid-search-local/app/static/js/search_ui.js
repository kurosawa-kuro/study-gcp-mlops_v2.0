(function () {
  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function yen(value) {
    return typeof value === "number" ? value.toLocaleString("ja-JP") + "円" : "賃料未設定";
  }

  function boolBadge(value) {
    if (value === true) return "ペット可";
    if (value === false) return "ペット不可";
    return "条件未設定";
  }

  function num(value, digits) {
    if (typeof value !== "number" || Number.isNaN(value)) return "不明";
    return digits > 0 ? value.toFixed(digits) : String(value);
  }

  function assessComponents(results) {
    const lexicalActive = results.some((item) => Number.isInteger(item.lexical_rank) && item.lexical_rank < 10000);
    const semanticActive = results.some(
      (item) =>
        (Number.isInteger(item.semantic_rank) && item.semantic_rank < 10000) ||
        (typeof item.me5_score === "number" && item.me5_score > 0),
    );
    const rerankActive = results.some((item) => item.score != null);
    const rerankChanged = rerankActive && results.some((item) => item.final_rank !== item.lexical_rank);
    return {
      lexical: {
        active: lexicalActive,
        label: lexicalActive ? "OK" : "信号なし",
        note: lexicalActive
          ? "lexical_rank を持つ候補を取得できています。"
          : "lexical 候補が見えていません。",
      },
      semantic: {
        active: semanticActive,
        label: semanticActive ? "OK" : "信号なし",
        note: semanticActive
          ? "semantic_rank または me5_score を確認できました。"
          : "semantic 側の信号が見えていません。",
      },
      rerank: {
        active: rerankActive,
        label: rerankActive ? "OK" : "未実行",
        note: !rerankActive
          ? "score が返っていないため rerank 無効の可能性があります。"
          : rerankChanged
            ? "final_rank と lexical_rank が異なり、rerank が順位へ反映されています。"
            : "score は返っています。今回の条件では順位変動は小さめです。",
      },
    };
  }

  function renderPropertyCard(result, index) {
    const title = escapeHtml(result.title || result.property_id);
    const propertyId = escapeHtml(result.property_id);
    const location = escapeHtml([result.city, result.ward].filter(Boolean).join(" ") || "所在地未設定");
    const specs = [
      escapeHtml(result.layout || "間取り不明"),
      typeof result.area_m2 === "number" ? escapeHtml(result.area_m2.toFixed(1) + "m2") : "面積不明",
      typeof result.walk_min === "number" ? escapeHtml("駅徒歩" + result.walk_min + "分") : "徒歩不明",
      typeof result.age_years === "number" ? escapeHtml("築" + result.age_years + "年") : "築年不明",
    ];
    return (
      '<article data-property-id="' +
      propertyId +
      '" class="search-result-card">' +
      '<header>' +
      "<p><strong>" +
      escapeHtml(index + 1 + "位") +
      "</strong> <code>" +
      propertyId +
      "</code></p>" +
      "<h3>" +
      title +
      "</h3>" +
      "<p>" +
      location +
      "</p>" +
      "</header>" +
      "<p><strong>" +
      escapeHtml(yen(result.rent)) +
      "</strong> ・ " +
      specs.join(" ・ ") +
      "</p>" +
      "<p>" +
      escapeHtml(boolBadge(result.pet_ok)) +
      "</p>" +
      "</article>"
    );
  }

  function buildFilters(root) {
    const filters = {};
    const maxRent = parseInt(root.querySelector("#q-max-rent")?.value || "", 10);
    if (!Number.isNaN(maxRent)) filters.max_rent = maxRent;
    const layout = (root.querySelector("#q-layout")?.value || "").trim();
    if (layout) filters.layout = layout;
    const maxWalkMin = parseInt(root.querySelector("#q-max-walk-min")?.value || "", 10);
    if (!Number.isNaN(maxWalkMin)) filters.max_walk_min = maxWalkMin;
    const maxAge = parseInt(root.querySelector("#q-max-age")?.value || "", 10);
    if (!Number.isNaN(maxAge)) filters.max_age = maxAge;
    if (root.querySelector("#q-pet-ok")?.checked) filters.pet_ok = true;
    return filters;
  }

  function renderComponentStatus(root, results) {
    const summary = assessComponents(results);
    [["lexical", summary.lexical], ["semantic", summary.semantic], ["rerank", summary.rerank]].forEach(
      ([name, status]) => {
        const stateNode = root.querySelector("#component-" + name + "-state");
        const noteNode = root.querySelector("#component-" + name + "-note");
        if (!stateNode || !noteNode) return;
        stateNode.textContent = status.label;
        stateNode.classList.toggle("status-ok", status.active);
        stateNode.classList.toggle("status-warn", !status.active);
        noteNode.textContent = status.note;
      },
    );
  }

  async function loadInfo(root) {
    const btn = root.querySelector("#data-btn");
    const card = root.querySelector("#data-card");
    const tbody = root.querySelector("#data-rows");
    if (!btn || !card || !tbody) return;
    btn.setAttribute("aria-busy", "true");
    try {
      const res = await fetch("/model/info");
      const body = await res.json();
      tbody.innerHTML = "";
      Object.entries(body).forEach(([key, value]) => {
        const tr = document.createElement("tr");
        const rendered =
          typeof value === "boolean" ? (value ? "true" : "false") : value == null ? "null" : String(value);
        tr.innerHTML =
          "<th>" + escapeHtml(key) + "</th><td><code>" + escapeHtml(rendered) + "</code></td>";
        tbody.appendChild(tr);
      });
      card.hidden = false;
    } finally {
      btn.removeAttribute("aria-busy");
    }
  }

  function init(config) {
    const root = document.getElementById(config.rootId);
    if (!root) return;

    let lastRequestId = null;
    const form = root.querySelector("#search-form");
    const feedbackForm = root.querySelector("#feedback-form");
    const infoBtn = root.querySelector("#data-btn");

    async function runSearch() {
      const button = root.querySelector("#search-btn");
      const state = root.querySelector("#search-state");
      const resultCard = root.querySelector("#result-card");
      const meta = root.querySelector("#result-meta");
      const cards = root.querySelector("#result-rows");
      const debug = root.querySelector("#debug-rows");
      const resultJson = root.querySelector("#result-json");
      if (!button || !state || !resultCard || !meta || !cards) return;

      button.setAttribute("aria-busy", "true");
      state.textContent = "検索中です...";
      const payload = {
        query: root.querySelector("#q-query")?.value || "",
        filters: buildFilters(root),
        top_k: parseInt(root.querySelector("#q-top-k")?.value || "", 10) || 20,
      };
      const explain = root.querySelector("#q-explain")?.checked === true;
      const url = explain ? "/search?explain=true" : "/search";

      try {
        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const body = await res.json();
        const results = body.results || [];
        lastRequestId = body.request_id || null;
        resultCard.hidden = false;
        meta.textContent =
          "request_id=" +
          (lastRequestId || "-") +
          " ・ status=" +
          res.status +
          " ・ " +
          results.length +
          " 件";
        state.textContent = res.ok ? "検索完了。結果を更新しました。" : "API がエラーを返しました。";
        cards.innerHTML = "";
        results.forEach((result, index) => {
          const wrap = document.createElement("div");
          wrap.innerHTML = renderPropertyCard(result, index);
          const card = wrap.firstElementChild;
          if (!card) return;
          card.addEventListener("click", function () {
            const fbPid = root.querySelector("#fb-pid");
            if (fbPid) fbPid.value = result.property_id;
          });
          cards.appendChild(card);
        });

        if (debug) {
          debug.innerHTML = "";
          results.forEach((result, index) => {
            const tr = document.createElement("tr");
            tr.innerHTML =
              "<td>" +
              escapeHtml(index + 1) +
              "</td>" +
              "<td><code>" +
              escapeHtml(result.property_id) +
              "</code></td>" +
              "<td>" +
              escapeHtml(result.final_rank ?? "") +
              "</td>" +
              "<td>" +
              escapeHtml(result.lexical_rank ?? "") +
              "</td>" +
              "<td>" +
              escapeHtml(result.semantic_rank ?? "") +
              "</td>" +
              "<td>" +
              escapeHtml(num(result.me5_score ?? 0, 4)) +
              "</td>" +
              "<td>" +
              (result.score == null ? "<em>n/a</em>" : escapeHtml(num(result.score, 4))) +
              "</td>" +
              "<td>" +
              (result.popularity_score == null
                ? "<em>n/a</em>"
                : escapeHtml(num(result.popularity_score, 4))) +
              "</td>";
            debug.appendChild(tr);
          });
        }

        if (resultJson) {
          resultJson.textContent = JSON.stringify(body, null, 2);
        }

        if (config.mode === "dev") {
          renderComponentStatus(root, results);
        }

        const first = results[0];
        const fbPid = root.querySelector("#fb-pid");
        if (first && fbPid) fbPid.value = first.property_id;
      } catch (error) {
        meta.textContent = "error: " + error;
        state.textContent = "検索に失敗しました。";
      } finally {
        button.removeAttribute("aria-busy");
      }
    }

    async function sendFeedback() {
      const resultNode = root.querySelector("#fb-result");
      if (!lastRequestId) {
        window.alert("まず検索を実行してください (request_id が必要)");
        return;
      }
      const payload = {
        request_id: lastRequestId,
        property_id: root.querySelector("#fb-pid")?.value || "",
        action: root.querySelector("#fb-action")?.value || "click",
      };
      const res = await fetch("/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await res.json().catch(function () {
        return {};
      });
      if (resultNode) {
        resultNode.textContent = JSON.stringify({ status: res.status, body: body }, null, 2);
      }
    }

    if (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        void runSearch();
      });
    }

    if (feedbackForm) {
      feedbackForm.addEventListener("submit", function (event) {
        event.preventDefault();
        void sendFeedback();
      });
    }

    if (infoBtn) {
      infoBtn.addEventListener("click", function () {
        void loadInfo(root);
      });
      void loadInfo(root);
    }
  }

  window.HybridSearchUI = { init: init };
})();
