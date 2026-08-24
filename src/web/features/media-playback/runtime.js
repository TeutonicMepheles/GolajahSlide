    class MediaPlayback {
      constructor(options = {}) {
        this.stage = options.stage || document.getElementById("deckStage");
        this.fullscreenTimeoutMs = options.fullscreenTimeoutMs || 900;
        this.records = [];
        this.recordByVideo = new WeakMap();
        this.fullscreenRecord = null;
        this.fullscreenMode = null;
        this.pendingRecord = null;
        this.requestSequence = 0;
        this.nativeExitPending = false;
        this.backgroundState = [];
        this.editing = document.body.classList.contains("editor-open");
        this.controlSequence = 0;
        this.overlay = document.createElement("div");
        this.overlay.className = "video-fullscreen-overlay";
        this.overlay.hidden = true;
        this.overlay.setAttribute("aria-hidden", "true");
        this.overlay.setAttribute("role", "dialog");
        this.overlay.setAttribute("aria-modal", "true");
        this.overlay.setAttribute("aria-label", "视频全屏播放");
        document.body.appendChild(this.overlay);
        this.reconcile();
        this.bind();
        this.syncControlScale();
        this.sync();
      }
      get fullscreenShell() { return this.fullscreenRecord?.shell || null; }
      get isFullscreen() { return Boolean(this.fullscreenRecord || this.pendingRecord || this.nativeExitPending); }
      bind() {
        this.handleFullscreenChange = this.handleFullscreenChange.bind(this);
        document.addEventListener("fullscreenchange", this.handleFullscreenChange);
        document.addEventListener("webkitfullscreenchange", this.handleFullscreenChange);
        addEventListener("resize", () => this.syncControlScale());
        addEventListener("keydown", event => {
          if (event.key === "Escape" && this.pendingRecord) {
            const record = this.pendingRecord;
            event.preventDefault();
            event.stopImmediatePropagation();
            this.cancelPending();
            if (this.recordIsVisible(record) && !this.editing) record.button.focus({preventScroll: true});
            return;
          }
          if (this.fullscreenMode !== "fallback") return;
          if (event.key === "Escape") {
            event.preventDefault();
            event.stopImmediatePropagation();
            this.exitFullscreen();
            return;
          }
          if (event.key !== "Tab" || !this.fullscreenRecord) return;
          const {video, closeButton, shell} = this.fullscreenRecord;
          const focusables = [video, closeButton].filter(node => !node.disabled && getComputedStyle(node).display !== "none");
          if (!focusables.length) return;
          const first = focusables[0];
          const last = focusables[focusables.length - 1];
          const active = document.activeElement;
          if (!shell.contains(active) || (!event.shiftKey && active === last) || (event.shiftKey && active === first)) {
            event.preventDefault();
            event.stopImmediatePropagation();
            (event.shiftKey ? last : first).focus({preventScroll: true});
          }
        }, true);
        this.observer = new MutationObserver(records => {
          const editingChanged = records.some(record => record.target === document.body);
          if (editingChanged) this.setEditing(document.body.classList.contains("editor-open"));
          if (records.some(record => (
            record.target === document.body ||
            record.target.classList?.contains("slide") ||
            record.target.hasAttribute?.("data-media-panel")
          ))) this.sync();
        });
        this.observer.observe(document.body, {subtree: true, attributes: true, attributeFilter: ["class"]});
      }
      createRecord(video) {
        const shell = video.closest("[data-slide-video-shell]");
        if (!shell) return null;
        const label = video.getAttribute("aria-label") || "视频";
        let button = shell.querySelector(":scope > [data-video-fullscreen]");
        if (!button) {
          button = document.createElement("button");
          button.type = "button";
          button.className = "video-fullscreen-button";
          button.dataset.videoFullscreen = "";
          button.textContent = "⛶";
          shell.appendChild(button);
        }
        let closeButton = shell.querySelector(":scope > .video-fullscreen-close");
        if (!closeButton) {
          closeButton = document.createElement("button");
          closeButton.type = "button";
          closeButton.className = "video-fullscreen-close";
          closeButton.textContent = "×";
          shell.appendChild(closeButton);
        }
        let status = shell.querySelector(":scope > .video-fullscreen-status");
        if (!status) {
          status = document.createElement("span");
          status.className = "video-fullscreen-status";
          status.setAttribute("aria-live", "polite");
          shell.appendChild(status);
        }
        button.setAttribute("aria-label", `全屏播放：${label}`);
        button.setAttribute("title", `全屏播放：${label}`);
        button.setAttribute("aria-pressed", "false");
        closeButton.setAttribute("aria-label", `退出全屏：${label}`);
        closeButton.setAttribute("title", `退出全屏：${label}`);
        const record = {
          video,
          shell,
          button,
          closeButton,
          status,
          label,
          originSlide: shell.closest(".slide"),
          originPanel: shell.closest("[data-media-panel]"),
          originParent: shell.parentNode,
          originNext: shell.nextSibling,
          placeholder: null,
          controlsPrepared: false,
          hadControls: video.controls,
          restoreFocusOnExit: true,
          pendingToken: null,
          exitPending: false,
        };
        button.addEventListener("click", event => {
          event.preventDefault();
          event.stopPropagation();
          if (!this.editing) this.toggleFullscreen(record);
        });
        closeButton.addEventListener("click", event => {
          event.preventDefault();
          event.stopPropagation();
          this.exitFullscreen();
        });
        ["click", "dblclick", "pointerdown", "touchstart", "touchend", "wheel"].forEach(type => {
          video.addEventListener(type, event => event.stopPropagation(), {passive: type !== "wheel"});
        });
        video.addEventListener("webkitbeginfullscreen", () => {
          if (this.pendingRecord === record) this.finishPending(record, record.pendingToken, {restoreControls: false});
          if (this.canEnterFullscreen(record)) this.activateFullscreen(record, "webkit-video");
          else if (typeof video.webkitExitFullscreen === "function") {
            try { video.webkitExitFullscreen(); } catch (_) { /* The browser owns an already closing native player. */ }
          }
        });
        video.addEventListener("webkitendfullscreen", () => {
          if (this.fullscreenRecord === record && this.fullscreenMode === "webkit-video") {
            this.clearFullscreen(record, {restoreFocus: record.restoreFocusOnExit});
          }
        });
        this.recordByVideo.set(video, record);
        return record;
      }
      reconcile(scope = document) {
        this.records = this.records.filter(record => record.shell.isConnected || record === this.fullscreenRecord || record === this.pendingRecord);
        const candidates = [];
        if (scope.matches?.("[data-slide-video]")) candidates.push(scope);
        scope.querySelectorAll?.("[data-slide-video]").forEach(video => candidates.push(video));
        candidates.forEach(video => {
          let record = this.recordByVideo.get(video);
          if (!record) record = this.createRecord(video);
          if (!record) return;
          if (!this.records.includes(record)) this.records.push(record);
          if (!record.placeholder) {
            record.originSlide = record.shell.closest(".slide");
            record.originPanel = record.shell.closest("[data-media-panel]");
            record.originParent = record.shell.parentNode;
            record.originNext = record.shell.nextSibling;
          }
          record.shell.classList.toggle("is-video-disabled", this.editing);
          record.button.disabled = this.editing || record === this.pendingRecord;
        });
        this.syncControlScale();
        this.sync();
      }
      recordFor(target) {
        if (!target) return null;
        if (target.video && target.shell) return target;
        if (target.matches?.("[data-slide-video]")) return this.recordByVideo.get(target) || null;
        const shell = target.matches?.("[data-slide-video-shell]") ? target : target.closest?.("[data-slide-video-shell]");
        return this.records.find(record => record.shell === shell) || null;
      }
      recordIsVisible(record) {
        return Boolean(record?.originSlide?.classList.contains("active") && (
          !record.originPanel || record.originPanel.classList.contains("active")
        ));
      }
      canEnterFullscreen(record) {
        return Boolean(record && !this.editing && record.shell.isConnected && this.recordIsVisible(record));
      }
      beginPending(record) {
        const token = ++this.requestSequence;
        this.pendingRecord = record;
        record.pendingToken = token;
        record.shell.classList.add("is-video-fullscreen-pending");
        record.button.disabled = true;
        record.status.textContent = "正在打开视频全屏";
        this.prepareControls(record);
        return token;
      }
      pendingIsCurrent(record, token) {
        return this.pendingRecord === record && record.pendingToken === token;
      }
      finishPending(record, token, {restoreControls = false} = {}) {
        if (!this.pendingIsCurrent(record, token)) return false;
        this.pendingRecord = null;
        record.pendingToken = null;
        record.shell.classList.remove("is-video-fullscreen-pending");
        record.button.disabled = this.editing;
        if (restoreControls) this.restoreControls(record);
        return true;
      }
      cancelPending({restoreControls = true} = {}) {
        const record = this.pendingRecord;
        if (!record) return;
        this.requestSequence += 1;
        this.pendingRecord = null;
        record.pendingToken = null;
        record.shell.classList.remove("is-video-fullscreen-pending");
        record.button.disabled = this.editing;
        record.status.textContent = "已取消打开视频全屏";
        if (restoreControls) this.restoreControls(record);
      }
      lockFallbackBackground() {
        if (this.backgroundState.length) return;
        const selectors = [
          ".deck-viewport", ".control-hotzone", ".deck-controls", ".deck-status",
          ".layout-editor-panel", ".visual-widget-overlay"
        ];
        this.backgroundState = selectors
          .map(selector => document.querySelector(`body > ${selector}`))
          .filter(Boolean)
          .map(node => ({
            node,
            hadInert: node.hasAttribute("inert"),
            ariaHidden: node.hasAttribute("aria-hidden") ? node.getAttribute("aria-hidden") : null,
          }));
        this.backgroundState.forEach(({node, hadInert, ariaHidden}) => {
          node.dataset.videoFullscreenBackground = "true";
          node.dataset.videoFullscreenPrevInert = String(hadInert);
          node.dataset.videoFullscreenPrevAriaHidden = ariaHidden === null ? "__missing__" : ariaHidden;
          node.setAttribute("inert", "");
          node.setAttribute("aria-hidden", "true");
        });
      }
      unlockFallbackBackground() {
        this.backgroundState.forEach(({node, hadInert, ariaHidden}) => {
          if (hadInert) node.setAttribute("inert", "");
          else node.removeAttribute("inert");
          if (ariaHidden === null) node.removeAttribute("aria-hidden");
          else node.setAttribute("aria-hidden", ariaHidden);
          delete node.dataset.videoFullscreenBackground;
          delete node.dataset.videoFullscreenPrevInert;
          delete node.dataset.videoFullscreenPrevAriaHidden;
        });
        this.backgroundState = [];
      }
      prepareControls(record) {
        if (record.controlsPrepared) return;
        record.hadControls = record.video.controls;
        record.controlsPrepared = true;
        if (!record.hadControls) {
          record.video.controls = true;
          record.video.dataset.videoFullscreenControlsAdded = "true";
        }
      }
      restoreControls(record) {
        if (!record.controlsPrepared) return;
        if (!record.hadControls) record.video.controls = false;
        delete record.video.dataset.videoFullscreenControlsAdded;
        record.controlsPrepared = false;
      }
      activateFullscreen(record, mode) {
        if (!this.canEnterFullscreen(record)) return false;
        if (this.pendingRecord === record) this.finishPending(record, record.pendingToken, {restoreControls: false});
        if (this.fullscreenRecord && this.fullscreenRecord !== record) {
          this.clearFullscreen(this.fullscreenRecord, {restoreFocus: false});
        }
        this.prepareControls(record);
        this.fullscreenRecord = record;
        this.fullscreenMode = mode;
        record.shell.classList.add("is-video-fullscreen");
        record.shell.classList.toggle("is-fallback-fullscreen", mode === "fallback");
        record.button.setAttribute("aria-label", `退出全屏：${record.label}`);
        record.button.setAttribute("title", `退出全屏：${record.label}`);
        record.button.setAttribute("aria-pressed", "true");
        record.status.textContent = "视频已进入全屏";
        document.body.classList.add("video-fullscreen-open");
        if (mode === "native-shell" || mode === "fallback") record.closeButton.focus({preventScroll: true});
        return true;
      }
      enterFallback(record) {
        if (!this.canEnterFullscreen(record) || this.fullscreenRecord && this.fullscreenRecord !== record) {
          this.restoreControls(record);
          return false;
        }
        if (!record.placeholder) {
          const token = `video-fullscreen-${++this.controlSequence}`;
          const placeholder = document.createElement("span");
          placeholder.hidden = true;
          placeholder.dataset.videoFullscreenPlaceholder = token;
          record.originParent = record.shell.parentNode;
          record.originNext = record.shell.nextSibling;
          record.shell.dataset.videoFullscreenId = token;
          record.shell.before(placeholder);
          record.placeholder = placeholder;
          this.overlay.appendChild(record.shell);
        }
        this.lockFallbackBackground();
        this.overlay.hidden = false;
        this.overlay.setAttribute("aria-hidden", "false");
        if (!this.activateFullscreen(record, "fallback")) {
          this.restoreFallback(record);
          this.restoreControls(record);
          return false;
        }
        return true;
      }
      async requestElementFullscreen(record, request, token) {
        let timeoutId = null;
        try {
          const result = request.call(record.shell);
          await Promise.race([
            Promise.resolve(result),
            new Promise((_, reject) => { timeoutId = setTimeout(() => reject(new Error("fullscreen timeout")), this.fullscreenTimeoutMs); })
          ]);
          clearTimeout(timeoutId);
          if (!this.pendingIsCurrent(record, token)) return this.fullscreenRecord === record;
          if (!this.canEnterFullscreen(record)) {
            this.finishPending(record, token, {restoreControls: true});
            return false;
          }
          const nativeElement = document.fullscreenElement || document.webkitFullscreenElement;
          if (nativeElement !== record.shell && nativeElement !== record.video) throw new Error("fullscreen not activated");
          this.finishPending(record, token, {restoreControls: false});
          return this.activateFullscreen(record, nativeElement === record.video ? "native-video" : "native-shell");
        } catch (_) {
          clearTimeout(timeoutId);
          if (!this.pendingIsCurrent(record, token)) return this.fullscreenRecord === record;
          const canFallback = this.canEnterFullscreen(record);
          this.finishPending(record, token, {restoreControls: !canFallback});
          return canFallback ? this.enterFallback(record) : false;
        }
      }
      async toggleFullscreen(target) {
        const record = this.recordFor(target);
        if (!record || this.editing) return;
        if (this.pendingRecord === record) return;
        if (this.pendingRecord) this.cancelPending();
        if (this.fullscreenRecord === record) return this.exitFullscreen();
        if (this.fullscreenRecord) return this.exitFullscreen({restoreFocus: false});
        record.restoreFocusOnExit = true;
        const token = this.beginPending(record);
        const standardRequest = document.fullscreenEnabled !== false && typeof record.shell.requestFullscreen === "function"
          ? record.shell.requestFullscreen
          : null;
        const webkitVideoRequest = typeof record.video.webkitEnterFullscreen === "function" && record.video.webkitSupportsFullscreen !== false
          ? record.video.webkitEnterFullscreen
          : null;
        const legacyElementRequest = typeof record.shell.webkitRequestFullscreen === "function"
          ? record.shell.webkitRequestFullscreen
          : null;
        if (standardRequest) return this.requestElementFullscreen(record, standardRequest, token);
        if (webkitVideoRequest) {
          try {
            webkitVideoRequest.call(record.video);
            if (this.fullscreenRecord === record) return true;
            if (!this.pendingIsCurrent(record, token)) return false;
            const canActivate = this.canEnterFullscreen(record);
            this.finishPending(record, token, {restoreControls: !canActivate});
            return canActivate ? this.activateFullscreen(record, "webkit-video") : false;
          } catch (_) {
            if (!this.pendingIsCurrent(record, token)) return false;
            const canFallback = this.canEnterFullscreen(record);
            this.finishPending(record, token, {restoreControls: !canFallback});
            return canFallback ? this.enterFallback(record) : false;
          }
        }
        if (legacyElementRequest) return this.requestElementFullscreen(record, legacyElementRequest, token);
        this.finishPending(record, token, {restoreControls: false});
        return this.enterFallback(record);
      }
      handleFullscreenChange() {
        const nativeElement = document.fullscreenElement || document.webkitFullscreenElement;
        if (nativeElement) {
          const record = this.records.find(candidate => candidate.shell === nativeElement || candidate.video === nativeElement);
          if (!record) return;
          const mode = nativeElement === record.video ? "native-video" : "native-shell";
          if (this.fullscreenRecord === record) {
            if (this.fullscreenMode === "fallback") this.restoreFallback(record);
            this.activateFullscreen(record, mode);
          } else if (this.pendingRecord === record && this.canEnterFullscreen(record)) {
            this.finishPending(record, record.pendingToken, {restoreControls: false});
            this.activateFullscreen(record, mode);
          } else {
            this.exitUnexpectedNative(record);
          }
          return;
        }
        this.nativeExitPending = false;
        if (this.fullscreenRecord && this.fullscreenMode !== "fallback" && this.fullscreenMode !== "webkit-video") {
          const record = this.fullscreenRecord;
          this.clearFullscreen(record, {restoreFocus: record.restoreFocusOnExit});
        }
      }
      async exitUnexpectedNative(record) {
        if (this.nativeExitPending) return;
        this.nativeExitPending = true;
        const exit = document.exitFullscreen || document.webkitExitFullscreen || document.webkitCancelFullScreen;
        try {
          if (exit) await Promise.resolve(exit.call(document));
        } catch (_) { /* A browser-owned fullscreen surface remains navigation-blocking. */ }
        const nativeElement = document.fullscreenElement || document.webkitFullscreenElement;
        this.nativeExitPending = nativeElement === record.shell || nativeElement === record.video;
      }
      restoreFallback(record) {
        if (record.placeholder?.parentNode) {
          record.placeholder.parentNode.insertBefore(record.shell, record.placeholder);
          record.placeholder.remove();
        } else if (record.originParent?.isConnected) {
          if (record.originNext?.parentNode === record.originParent) record.originParent.insertBefore(record.shell, record.originNext);
          else record.originParent.appendChild(record.shell);
        } else if (record.originSlide?.isConnected) {
          const mediaRoot = record.originSlide.querySelector(".media-tabs, .media-grid, .split-media, .wide-media-stage, .gallery-stage, .chart-stage, .hero-visual");
          mediaRoot?.appendChild(record.shell);
        }
        record.placeholder = null;
        delete record.shell.dataset.videoFullscreenId;
        this.overlay.hidden = true;
        this.overlay.setAttribute("aria-hidden", "true");
        this.unlockFallbackBackground();
      }
      async exitFullscreen({restoreFocus = true} = {}) {
        if (this.pendingRecord) this.cancelPending();
        const record = this.fullscreenRecord;
        if (!record || record.exitPending) return !record;
        record.restoreFocusOnExit = restoreFocus;
        const nativeElement = document.fullscreenElement || document.webkitFullscreenElement;
        if (nativeElement && (nativeElement === record.shell || nativeElement === record.video)) {
          const exit = document.exitFullscreen || document.webkitExitFullscreen || document.webkitCancelFullScreen;
          if (!exit) return false;
          record.exitPending = true;
          try { await Promise.resolve(exit.call(document)); } catch (_) { /* Keep local state while the browser remains fullscreen. */ }
          record.exitPending = false;
          const remainingElement = document.fullscreenElement || document.webkitFullscreenElement;
          if (remainingElement === record.shell || remainingElement === record.video) return false;
        } else if (this.fullscreenMode === "webkit-video") {
          if (typeof record.video.webkitExitFullscreen !== "function") return false;
          record.exitPending = true;
          try {
            record.video.webkitExitFullscreen();
            return true;
          } catch (_) {
            record.exitPending = false;
            return false;
          }
        }
        if (this.fullscreenRecord === record) this.clearFullscreen(record, {restoreFocus});
        return true;
      }
      clearFullscreen(record, {restoreFocus = true} = {}) {
        if (!record) return;
        if (record.placeholder || record.shell.parentNode === this.overlay) this.restoreFallback(record);
        record.shell.classList.remove("is-video-fullscreen", "is-fallback-fullscreen", "is-video-fullscreen-pending");
        record.button.setAttribute("aria-label", `全屏播放：${record.label}`);
        record.button.setAttribute("title", `全屏播放：${record.label}`);
        record.button.setAttribute("aria-pressed", "false");
        record.button.disabled = this.editing;
        record.status.textContent = "视频已退出全屏";
        record.exitPending = false;
        this.restoreControls(record);
        if (this.fullscreenRecord === record) {
          this.fullscreenRecord = null;
          this.fullscreenMode = null;
        }
        document.body.classList.remove("video-fullscreen-open");
        const originIsVisible = record.originSlide?.classList.contains("active") && (!record.originPanel || record.originPanel.classList.contains("active"));
        if (restoreFocus && !this.editing && originIsVisible) record.button.focus({preventScroll: true});
      }
      handleSlideChange() {
        this.cancelPending();
        if (this.fullscreenRecord) this.exitFullscreen({restoreFocus: false});
        this.sync();
      }
      setEditing(editing) {
        this.editing = Boolean(editing);
        if (this.pendingRecord) this.cancelPending();
        this.records.forEach(record => {
          record.shell.classList.toggle("is-video-disabled", this.editing);
          record.button.disabled = this.editing || record === this.pendingRecord;
        });
        if (this.editing && this.fullscreenRecord) this.exitFullscreen({restoreFocus: false});
      }
      syncControlScale() {
        const scale = Math.max(.001, Number(this.stage?.dataset.scale) || 1);
        this.records.forEach(record => {
          /* A one-pixel screen-space margin absorbs transformed-stage rounding. */
          record.shell.style.setProperty("--video-control-size", `${45 / scale}px`);
          record.shell.style.setProperty("--video-control-offset", `${14 / scale}px`);
          record.shell.style.setProperty("--video-control-icon-size", `${20 / scale}px`);
        });
      }
      sync() {
        this.records.forEach(record => {
          const panelIsActive = !record.originPanel || record.originPanel.classList.contains("active");
          const isVisible = record.originSlide?.classList.contains("active") && panelIsActive;
          if (!isVisible) {
            if (this.pendingRecord === record) this.cancelPending();
            if (this.fullscreenRecord === record) this.exitFullscreen({restoreFocus: false});
            if (!record.video.paused) record.video.pause();
            return;
          }
          if (record.video.hasAttribute("data-video-autoplay") && record.video.paused) {
            const playPromise = record.video.play();
            if (playPromise?.catch) playPromise.catch(() => {});
          }
        });
      }
      sanitizeClone(clone) {
        clone.querySelectorAll(".video-fullscreen-overlay").forEach(overlay => {
          overlay.querySelectorAll("[data-video-fullscreen-id]").forEach(shell => {
            const token = shell.dataset.videoFullscreenId;
            const placeholder = [...clone.querySelectorAll("[data-video-fullscreen-placeholder]")]
              .find(node => node.dataset.videoFullscreenPlaceholder === token);
            if (placeholder?.parentNode) placeholder.parentNode.insertBefore(shell, placeholder);
          });
          overlay.remove();
        });
        clone.querySelectorAll("[data-video-fullscreen-placeholder]").forEach(node => node.remove());
        clone.querySelectorAll("[data-video-fullscreen-background]").forEach(node => {
          if (node.dataset.videoFullscreenPrevInert === "true") node.setAttribute("inert", "");
          else node.removeAttribute("inert");
          const ariaHidden = node.dataset.videoFullscreenPrevAriaHidden;
          if (ariaHidden === "__missing__") node.removeAttribute("aria-hidden");
          else if (ariaHidden !== undefined) node.setAttribute("aria-hidden", ariaHidden);
          node.removeAttribute("data-video-fullscreen-background");
          node.removeAttribute("data-video-fullscreen-prev-inert");
          node.removeAttribute("data-video-fullscreen-prev-aria-hidden");
        });
        clone.querySelectorAll(".video-fullscreen-button, .video-fullscreen-close, .video-fullscreen-status").forEach(node => node.remove());
        clone.querySelectorAll("[data-video-fullscreen-controls-added]").forEach(video => {
          video.removeAttribute("controls");
          video.removeAttribute("data-video-fullscreen-controls-added");
        });
        clone.querySelectorAll("[data-slide-video-shell]").forEach(shell => {
          shell.classList.remove("is-video-fullscreen", "is-fallback-fullscreen", "is-video-fullscreen-pending", "is-video-disabled");
          shell.removeAttribute("data-video-fullscreen-id");
          shell.style.removeProperty("--video-control-size");
          shell.style.removeProperty("--video-control-offset");
          shell.style.removeProperty("--video-control-icon-size");
        });
        clone.querySelector("body")?.classList.remove("video-fullscreen-open");
      }
    }
