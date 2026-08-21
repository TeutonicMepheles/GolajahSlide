    /* ===========================================
       PRESENTER HOVER FOCUS
       =========================================== */
    class PresenterFocus {
      constructor(shortcut = "H") {
        this.button = document.getElementById("focus");
        this.enabled = true;
        const normalizedShortcut = this.normalizeShortcut(shortcut);
        this.shortcut = normalizedShortcut && !this.isReservedShortcut(normalizedShortcut) ? normalizedShortcut : "H";
        this.pointerFrame = null;
        this.pendingPointer = null;
        this.pointerCue = this.createPointerCue();
        this.registerTextTargets();
        this.button.addEventListener("click", () => this.toggle());
        addEventListener("keydown", event => {
          if (event.defaultPrevented || event.repeat ||
              event.target.isContentEditable ||
              event.target.closest?.("button,input,textarea,select,a,[contenteditable=true]") ||
              !this.matchesShortcut(event)) return;
          event.preventDefault();
          this.toggle();
        });
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
      normalizeShortcut(value) {
        if (typeof value !== "string") return null;
        const parts = value.split("+").map(part => part.trim()).filter(Boolean);
        if (!parts.length) return null;
        const aliases = {control:"Ctrl", ctrl:"Ctrl", alt:"Alt", shift:"Shift", meta:"Meta", cmd:"Meta", command:"Meta"};
        const modifiers = new Set();
        let key = null;
        for (const part of parts) {
          const modifier = aliases[part.toLowerCase()];
          if (modifier) modifiers.add(modifier);
          else if (key === null) key = part.length === 1 ? part.toUpperCase() : part.toUpperCase();
          else return null;
        }
        if (!key || !/^(?:[A-Z0-9]|F(?:[1-9]|1[0-2]))$/.test(key)) return null;
        const prefix = ["Ctrl", "Alt", "Shift", "Meta"].filter(name => modifiers.has(name));
        return [...prefix, key].join("+");
      }
      shortcutFromEvent(event) {
        if (["Control", "Alt", "Shift", "Meta"].includes(event.key)) return null;
        const key = event.key.length === 1 ? event.key.toUpperCase() : event.key.toUpperCase();
        return this.normalizeShortcut([
          event.ctrlKey ? "Ctrl" : "",
          event.altKey ? "Alt" : "",
          event.shiftKey ? "Shift" : "",
          event.metaKey ? "Meta" : "",
          key
        ].filter(Boolean).join("+"));
      }
      isReservedShortcut(value) {
        const shortcut = this.normalizeShortcut(value);
        if (!shortcut) return true;
        const key = shortcut.split("+").at(-1);
        return key === "A" || key === "F" || shortcut === "E";
      }
      matchesShortcut(event) {
        return this.shortcutFromEvent(event) === this.shortcut;
      }
      ariaShortcut() {
        return this.shortcut.replace("Ctrl", "Control");
      }
      setShortcut(value) {
        const shortcut = this.normalizeShortcut(value);
        if (!shortcut || this.isReservedShortcut(shortcut)) return false;
        this.shortcut = shortcut;
        this.refreshControl();
        return true;
      }
      refreshControl() {
        this.button.setAttribute("aria-keyshortcuts", this.ariaShortcut());
        this.button.setAttribute("aria-label", this.enabled ? "关闭悬浮聚焦" : "开启悬浮聚焦");
        this.button.title = `${this.enabled ? "关闭" : "开启"}悬浮聚焦（${this.shortcut}）`;
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
        this.refreshControl();
        if (!this.enabled) this.hidePointer();
      }
      toggle() { this.setEnabled(!this.enabled); }
    }
