    /* ===========================================
       CITATIONS
       =========================================== */
    class Citations {
      constructor() {
        this.active = null;
        this.hideTimer = null;
        this.tooltip = this.createTooltip();
        document.addEventListener("pointerover", event => this.onPointerOver(event));
        document.addEventListener("pointerout", event => this.onPointerOut(event));
        document.addEventListener("focusin", event => this.onFocusIn(event));
        document.addEventListener("focusout", event => this.onFocusOut(event));
        document.addEventListener("keydown", event => {
          if (event.key === "Escape") this.hide(true);
        });
        addEventListener("resize", () => this.active && this.position());
        this.tooltip.addEventListener("pointerenter", () => this.cancelHide());
        this.tooltip.addEventListener("pointerleave", () => this.scheduleHide());
      }
      createTooltip() {
        const tooltip = document.createElement("aside");
        tooltip.className = "citation-tooltip";
        tooltip.id = "citationTooltip";
        tooltip.dataset.open = "false";
        tooltip.setAttribute("role", "tooltip");
        tooltip.innerHTML = '<span class="citation-tooltip-number"></span><p class="citation-tooltip-text"></p><a class="citation-tooltip-link" target="_blank" rel="noreferrer"></a>';
        document.body.appendChild(tooltip);
        return tooltip;
      }
      reference(target) { return target.closest?.(".citation-ref") || null; }
      onPointerOver(event) {
        const ref = this.reference(event.target);
        if (ref) this.show(ref);
      }
      onPointerOut(event) {
        const ref = this.reference(event.target);
        if (ref && !ref.contains(event.relatedTarget) && !this.tooltip.contains(event.relatedTarget)) this.scheduleHide();
      }
      onFocusIn(event) {
        const ref = this.reference(event.target);
        if (ref) this.show(ref);
      }
      onFocusOut(event) {
        const ref = this.reference(event.target);
        if (ref && !this.tooltip.contains(event.relatedTarget)) this.scheduleHide();
      }
      cancelHide() {
        if (this.hideTimer !== null) clearTimeout(this.hideTimer);
        this.hideTimer = null;
      }
      scheduleHide() {
        this.cancelHide();
        this.hideTimer = setTimeout(() => this.hide(), 120);
      }
      show(ref) {
        this.cancelHide();
        if (this.active && this.active !== ref) this.active.setAttribute("aria-expanded", "false");
        this.active = ref;
        const number = ref.dataset.citationNumber;
        const link = this.tooltip.querySelector(".citation-tooltip-link");
        this.tooltip.querySelector(".citation-tooltip-number").textContent = `引用 ${number}`;
        this.tooltip.querySelector(".citation-tooltip-text").textContent = ref.dataset.citationText || "";
        link.textContent = `${ref.dataset.citationUrl}  ↗`;
        link.href = ref.href;
        ref.setAttribute("aria-describedby", this.tooltip.id);
        ref.setAttribute("aria-expanded", "true");
        this.tooltip.dataset.open = "true";
        this.position();
      }
      position() {
        if (!this.active) return;
        const anchor = this.active.getBoundingClientRect();
        const tip = this.tooltip.getBoundingClientRect();
        const gap = 12;
        const edge = 16;
        let left = anchor.left + anchor.width / 2 - tip.width / 2;
        left = Math.max(edge, Math.min(innerWidth - tip.width - edge, left));
        let top = anchor.bottom + gap;
        if (top + tip.height > innerHeight - edge) top = anchor.top - tip.height - gap;
        top = Math.max(edge, Math.min(innerHeight - tip.height - edge, top));
        this.tooltip.style.left = `${Math.round(left)}px`;
        this.tooltip.style.top = `${Math.round(top)}px`;
      }
      hide(returnFocus = false) {
        this.cancelHide();
        const previous = this.active;
        if (previous) previous.setAttribute("aria-expanded", "false");
        this.active = null;
        this.tooltip.dataset.open = "false";
        if (returnFocus && previous && document.activeElement === this.tooltip.querySelector("a")) previous.focus();
      }
    }
