    /* ===========================================
       PRESENTER HOVER FOCUS
       =========================================== */
    class PresenterFocus {
      constructor() {
        this.button = document.getElementById("focus");
        this.enabled = true;
        this.pointerFrame = null;
        this.pendingPointer = null;
        this.pointerCue = this.createPointerCue();
        this.registerTextTargets();
        this.button.addEventListener("click", () => this.toggle());
        document.addEventListener("pointermove", event => this.trackPointer(event), {passive:true});
        document.addEventListener("pointerout", event => {
          if (!event.relatedTarget) this.hidePointer();
        }, {passive:true});
        addEventListener("blur", () => this.hidePointer());
        document.addEventListener("visibilitychange", () => {
          if (document.hidden) this.hidePointer();
        });
        this.setEnabled(true);
      }
      createPointerCue() {
        const cue = document.querySelector("body > .presenter-pointer-cue") || document.createElement("span");
        cue.className = "presenter-pointer-cue";
        cue.removeAttribute("style");
        cue.dataset.visible = "false";
        cue.setAttribute("aria-hidden", "true");
        if (!cue.isConnected) document.body.appendChild(cue);
        return cue;
      }
      trackPointer(event) {
        if (!this.enabled || document.body.classList.contains("editor-open") ||
            (event.pointerType && !["mouse", "pen"].includes(event.pointerType)) ||
            !event.target.closest?.(".slide.active")) {
          this.hidePointer();
          return;
        }
        this.pendingPointer = {x:event.clientX, y:event.clientY};
        if (this.pointerFrame !== null) return;
        this.pointerFrame = requestAnimationFrame(() => {
          this.pointerFrame = null;
          if (!this.pendingPointer) return;
          this.pointerCue.style.left = `${this.pendingPointer.x}px`;
          this.pointerCue.style.top = `${this.pendingPointer.y}px`;
          this.pointerCue.dataset.visible = "true";
          this.pendingPointer = null;
        });
      }
      hidePointer() {
        this.pendingPointer = null;
        this.pointerCue.dataset.visible = "false";
      }
      registerTextTargets(root = document) {
        const selectors = [
          ":scope > h1",
          ":scope > h3",
          ":scope > p",
          ":scope > strong",
          ":scope > ul > li",
          ":scope > ol > li",
          ":scope > pre",
          ":scope table th",
          ":scope table td"
        ].join(",");
        root.querySelectorAll("[data-presenter-focus]").forEach(container => {
          container.querySelectorAll(selectors).forEach(node => {
            if (node.textContent.trim() && !node.hasAttribute("data-presenter-text")) {
              node.dataset.presenterText = "block";
            }
          });
        });
      }
      setEnabled(enabled) {
        this.enabled = Boolean(enabled);
        document.body.classList.toggle("presenter-focus-enabled", this.enabled);
        this.button.classList.toggle("active", this.enabled);
        this.button.setAttribute("aria-pressed", String(this.enabled));
        this.button.setAttribute("aria-label", this.enabled ? "关闭悬浮聚焦" : "开启悬浮聚焦");
        this.button.title = `${this.enabled ? "关闭" : "开启"}悬浮聚焦（H）`;
        if (!this.enabled) this.hidePointer();
      }
      toggle() { this.setEnabled(!this.enabled); }
    }
